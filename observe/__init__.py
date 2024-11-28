import json
import logging
import queue
import threading
import jsonschema
import time
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, constr, conlist, model_validator

from pathlib import Path
from typing import List, Callable, Optional, Dict, Any, Union
from cryptography.fernet import Fernet
from datetime import datetime


class BrokerException(Exception):
    """Broker base exception class."""
    pass


class SubscriberTypeException(BrokerException):
    """Exception raised when subscriber is not callable."""
    pass


class AuthorizationException(BrokerException):
    """Exception raised when a subscriber or message is unauthorized."""
    pass


# Nested data structure for the "data" field
class MessageDataItem(BaseModel):
    key: constr(pattern=r"^[\w\d_]+$", min_length=2, max_length=32) = Field(..., description="Key associated with the event or signal.")
    value: Union[str, int, float, bool, dict, list] = Field(..., description="Value associated with the event or signal.")
    type: constr(pattern=r"^(string|number|boolean|object|array)$") = Field(..., description="Type of the value.")
    description: constr(pattern=r"^[\w\d _\-,.!]+$", min_length=10, max_length=256) = Field(..., description="Description of the value.")

    @model_validator(mode="before")
    def validate_value_type(cls, values):
        """Ensure the value matches its declared type."""
        value, value_type = values.get("value"), values.get("type")
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        if value is not None and value_type in type_map and not isinstance(value, type_map[value_type]):
            raise ValueError(f"Value must match its declared type '{value_type}'.")
        return values

# Main Message class
class Message(BaseModel):
    message: constr(pattern=r"^[\w\d _\-,.!]+$", min_length=10, max_length=256) = Field(..., description="Message content.")
    version: constr(pattern=r"^\d+\.\d+\.\d+(-[0-9A-Za-z\.-]+)?(\+[0-9A-Za-z\.-]+)?$") = Field(..., description="Schema version.")
    messageId: UUID = Field(default_factory=uuid4, description="Unique identifier for the message.")
    correlationId: Optional[UUID] = Field(None, description="Identifier to correlate related messages.")
    priority: Optional[str] = Field(None, pattern=r"^(low|medium|high)$", description="Priority of the message.")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of message creation.")
    sender: constr(pattern=r"^[\w\d_\.-]+$", min_length=3, max_length=64) = Field(..., description="Sender's name.")
    tags: Optional[List[constr(pattern=r"^[\w\d_]+$", min_length=2, max_length=32)]] = Field(None, description="Associated tags.")
    data: Optional[conlist(MessageDataItem, unique_items=True)] = Field(None, description="Associated data items.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata.")

    class Config:
        schema_extra = {
            "example": {
                "message": "System health check completed.",
                "version": "1.0.0",
                "messageId": "9f6ad7b3-c8e5-4608-9e0a-129839a0a3ef",
                "timestamp": "2024-11-27T12:00:00Z",
                "sender": "health-check",
                "priority": "low",
                "tags": ["health", "system"],
                "data": [
                    {
                        "key": "uptime",
                        "value": 3600,
                        "type": "number",
                        "description": "System uptime in seconds."
                    }
                ],
                "metadata": {
                    "retry": True,
                    "attempts": 3
                }
            }
        }

    @model_validator(mode="before")
    def set_defaults(cls, values):
        """Set default values for optional fields if not explicitly provided."""
        values["timestamp"] = values.get("timestamp", datetime.utcnow())
        values["messageId"] = values.get("messageId", uuid4())
        return values

    def add_tag(self, tag: str):
        """Add a tag to the message."""
        if not self.tags:
            self.tags = []
        if tag not in self.tags:
            self.tags.append(tag)

    def add_data_item(self, key: str, value: Any, value_type: str, description: str):
        """Add a data item to the message."""
        if not self.data:
            self.data = []
        self.data.append(MessageDataItem(key=key, value=value, type=value_type, description=description))

    def to_dict(self) -> dict:
        """Convert the message to a dictionary."""
        return self.model_dump()

    def to_json(self) -> str:
        """Convert the message to a JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """Create a Message object from a JSON string."""
        return cls.parse_raw(json_str)



class Broker:
    _initialized = False
    _thread = None

    __instance__: Optional["Broker"] = None
    __message_queue__: queue.Queue = None
    __subscribers__: List[Callable] = None
    __shutdown_event__: threading.Event = None
    __lock__: threading.Lock = None  # Lock for thread-safety when modifying subscribers
    __rate_limit_lock__: threading.Lock = None  # Lock for rate limiting
    __auth_lock__: threading.Lock = None  # Lock for authentication-related checks

    # Encryption key (for simplicity, using an environment variable or secure location for production)
    encryption_key: str = Fernet.generate_key().decode("utf-8")
    cipher_suite: Fernet = Fernet(encryption_key)

    def __new__(cls):
        """Singleton pattern for Broker class."""
        if cls.__instance__ is None:
            cls.__instance__ = super(Broker, cls).__new__(cls)
        return cls.__instance__

    def __init__(self, queue_size: int = 100, max_rate_limit: int = 1000):
        """Initialize broker with logger, setup, rate limiting, and queue size."""
        if not self._initialized:
            self.logger = logging.getLogger(__name__)
            self._setup(queue_size, max_rate_limit)
            self._initialized = True

    def _run(self):
        """Main thread loop to process messages from the queue."""
        while not self.__shutdown_event__.is_set():
            try:
                message = self.queue.get(timeout=1)  # Adds timeout for graceful shutdown
                if message == "SHUTDOWN":
                    break
                self._notify_subscribers(message)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")

    def _setup(self, queue_size: int, max_rate_limit: int):
        """Initial setup for message queue, subscribers, rate limiting, and background thread."""
        self.__message_queue__ = queue.Queue(maxsize=queue_size)
        self.__subscribers__ = []
        self.__shutdown_event__ = threading.Event()
        self.__lock__ = threading.Lock()  # Protect subscribers list from concurrent access
        self.__rate_limit_lock__ = threading.Lock()  # Rate limit lock to control traffic flow
        self.__auth_lock__ = threading.Lock()  # Protect authentication logic
        self.max_rate_limit = max_rate_limit  # Max number of messages per second

        # Start the broker worker thread
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def queue(self):
        """Get the message queue."""
        return self.__message_queue__

    @property
    def subscribers(self):
        """Get the list of subscribers."""
        return self.__subscribers__

    def subscribe(self, subscriber: Callable, auth_token: Optional[str] = None):
        """Subscribe a callable to the broker with optional authorization."""
        if not callable(subscriber):
            raise SubscriberTypeException("Subscriber must be callable!")

        if auth_token:
            if not self._authorize_subscriber(auth_token):
                raise AuthorizationException("Subscriber authorization failed.")

        with self.__lock__:
            self.subscribers.append(subscriber)

    def unsubscribe(self, subscriber: Callable):
        """Unsubscribe a callable from the broker."""
        with self.__lock__:
            if subscriber in self.subscribers:
                self.subscribers.remove(subscriber)
            else:
                self.logger.warning("Subscriber not found.")

    def publish(self, envelope: Message, auth_token: Optional[str] = None):
        """Publish a message to the broker, validating, adding it to the queue, and optionally encrypting."""
        if not self._thread.is_alive():
            raise BrokerException("Broker is not running!")

        # Authentication check for the sender or publisher
        if auth_token and not self._authorize_publisher(auth_token):
            raise AuthorizationException("Publisher authorization failed.")

        # Rate limit check
        if not self._check_rate_limit():
            self.logger.warning("Rate limit exceeded, message discarded.")
            return

        # Convert the message object to a JSON string
        message = envelope.to_json()

        # Validate the message against the schema
        self._validate_message(message)

        # Optionally encrypt the message before sending
        encrypted_message = self._encrypt_message(message)

        # Add message to the queue based on priority
        message_obj = json.loads(encrypted_message)
        priority = message_obj.get('priority', 'medium')
        self._add_message_to_queue(encrypted_message, priority)

    def _check_rate_limit(self):
        """Check if the rate limit has been exceeded."""
        current_time = time.time()
        if not hasattr(self, "_last_check_time"):
            self._last_check_time = current_time
            self._message_count = 0

        if current_time - self._last_check_time < 1:
            if self._message_count >= self.max_rate_limit:
                return False
            self._message_count += 1
        else:
            self._last_check_time = current_time
            self._message_count = 1  # Reset message count

        return True

    def _add_message_to_queue(self, message: str, priority: str):
        """Add message to the queue based on priority."""
        if priority == 'high':
            # High priority messages get added to the front
            self.queue.put(message)
        else:
            if not self.queue.full():
                self.queue.put(message)
            else:
                self.logger.warning("Message queue is full, message discarded.")

    def _validate_message(self, message: str):
        """Validate the message against the predefined schema."""
        schema_path = Path(__file__).parent / "message_schema.json"

        try:
            with open(schema_path, "r") as json_schema_file:
                message_schema = json.load(json_schema_file)

            message_obj = json.loads(message)
            jsonschema.validate(message_obj, message_schema)
        except (json.JSONDecodeError, jsonschema.ValidationError, jsonschema.SchemaError) as e:
            self.logger.error(f"Error validating message: {e}")
            raise e
        except Exception as e:
            self.logger.error(f"Unexpected error during message validation: {e}")
            raise e

    def _notify_subscribers(self, message: str):
        """Notify all subscribers of a new message."""
        with self.__lock__:
            for subscriber in self.subscribers:
                try:
                    decrypted_message = self._decrypt_message(message)
                    subscriber(decrypted_message)
                except Exception as e:
                    self.logger.error(f"Error notifying subscriber: {e}")

    def _encrypt_message(self, message: str) -> str:
        """Encrypt the message before sending (if needed)."""
        encrypted_message = self.cipher_suite.encrypt(message.encode('utf-8'))
        return encrypted_message.decode('utf-8')

    def _decrypt_message(self, encrypted_message: str) -> str:
        """Decrypt the message when received."""
        try:
            decrypted_message = self.cipher_suite.decrypt(encrypted_message.encode('utf-8'))
            return decrypted_message.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Error decrypting message: {e}")
            raise e

    def _authorize_subscriber(self, auth_token: str) -> bool:
        """Authorize subscriber using an authorization token (e.g., API key)."""
        with self.__auth_lock__:
            # This is a simple mockup for authorization.
            valid_tokens = ["valid-token-1", "valid-token-2"]
            if auth_token in valid_tokens:
                return True
            return False

    def _authorize_publisher(self, auth_token: str) -> bool:
        """Authorize publisher using an authorization token."""
        with self.__auth_lock__:
            # Simulate authorization for publishers
            valid_publishers = ["trusted-publisher-1", "trusted-publisher-2"]
            if auth_token in valid_publishers:
                return True
            return False

    def shutdown(self, timeout: int = 10):
        """Gracefully shutdown the broker."""
        self.__shutdown_event__.set()  # Signal the thread to stop
        self.queue.put("SHUTDOWN")  # Add a shutdown message to the queue

        self._thread.join(timeout=timeout)  # Wait for the thread to finish gracefully
        self.logger.info("Broker shutdown complete.")

    def __del__(self):
        """Cleanup when Broker instance is deleted."""
        if self._thread.is_alive():
            self.shutdown()
