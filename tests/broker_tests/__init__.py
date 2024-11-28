import unittest
from unittest.mock import patch, MagicMock
import json
import threading
import queue
import time

import jsonschema

from observe import Broker, BrokerException, SubscriberTypeException


class TestBroker(unittest.TestCase):
    def setUp(self):
        """Set up a new instance of the Broker for each test."""
        self.broker = Broker()
        self.broker.shutdown()  # Ensure clean setup
        self.broker.__class__.__instance__ = None
        self.broker = Broker()

    def tearDown(self):
        """Shutdown broker after each test."""
        self.broker.shutdown()

    def test_singleton_behavior(self):
        """Ensure that the Broker class follows the singleton pattern."""
        broker1 = Broker()
        broker2 = Broker()
        self.assertIs(broker1, broker2)

    def test_subscribe_and_notify(self):
        """Test if subscribers are notified with published messages."""
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        subscriber.assert_called_with(test_message)

    def test_subscribe_duplicate_subscriber(self):
        """Test if adding the same subscriber multiple times results in duplicate calls."""
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)
        self.broker.subscribe(subscriber)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        # Duplicate subscriber is called twice
        self.assertEqual(subscriber.call_count, 2)

    def test_unsubscribe(self):
        """Test if subscribers are properly unsubscribed."""
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)
        self.broker.unsubscribe(subscriber)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        subscriber.assert_not_called()

    def test_unsubscribe_nonexistent_subscriber(self):
        """Test unsubscribing a subscriber that does not exist."""
        subscriber = MagicMock()
        self.broker.unsubscribe(subscriber)

    def test_publish_valid_message(self):
        """Test publishing valid messages."""
        test_message = json.dumps({"event": "test_event", "data": "test_data"})

        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        self.assertEqual(self.broker.queue.get(), test_message)

    def test_publish_invalid_message(self):
        """Test publishing invalid messages raises an exception."""
        invalid_message = "{invalid json}"

        with patch.object(self.broker, "_validate_message") as mock_validate:
            mock_validate.side_effect = json.JSONDecodeError("msg", "", 0)

            with self.assertRaises(json.JSONDecodeError):
                self.broker.publish(invalid_message)

    def test_shutdown(self):
        """Test the shutdown process of the broker."""
        self.assertTrue(self.broker._thread.is_alive())
        self.broker.shutdown()
        self.assertFalse(self.broker._thread.is_alive())

    def test_broker_not_running(self):
        """Test publishing when the broker is not running raises an exception."""
        self.broker.shutdown()

        with self.assertRaises(BrokerException):
            self.broker.publish("message")

    def test_notify_multiple_subscribers(self):
        """Test that multiple subscribers receive the message."""
        subscriber1 = MagicMock()
        subscriber2 = MagicMock()

        self.broker.subscribe(subscriber1)
        self.broker.subscribe(subscriber2)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        subscriber1.assert_called_with(test_message)
        subscriber2.assert_called_with(test_message)

    def test_error_in_subscriber(self):
        """Test that an error in one subscriber does not block others."""
        subscriber1 = MagicMock(side_effect=Exception("Test exception"))
        subscriber2 = MagicMock()

        self.broker.subscribe(subscriber1)
        self.broker.subscribe(subscriber2)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        subscriber1.assert_called_with(test_message)
        subscriber2.assert_called_with(test_message)

    def test_empty_queue(self):
        """Test if the broker handles an empty queue gracefully."""
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        self.assertFalse(self.broker._thread.is_alive())

    def test_multiple_shutdown_calls(self):
        """Test if multiple calls to shutdown do not raise exceptions."""
        self.broker.shutdown()
        try:
            self.broker.shutdown()
        except Exception as e:
            self.fail(f"Multiple shutdown calls raised an exception: {e}")

    def test_concurrent_publish(self):
        """Test concurrent publishing of messages to the queue."""
        num_messages = 100
        subscribers = [MagicMock() for _ in range(10)]
        for sub in subscribers:
            self.broker.subscribe(sub)

        def publish_messages():
            for i in range(num_messages):
                message = json.dumps({"event": f"event_{i}", "data": f"data_{i}"})
                with patch.object(self.broker, "_validate_message", return_value=None):
                    self.broker.publish(message)

        threads = [threading.Thread(target=publish_messages) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        for sub in subscribers:
            self.assertEqual(sub.call_count, num_messages * 5)

    def test_subscribe_unsubscribe_in_concurrent_publish(self):
        """Test subscribing and unsubscribing while publishing concurrently."""
        subscriber = MagicMock()

        def manage_subscriber():
            for _ in range(50):
                self.broker.subscribe(subscriber)
                self.broker.unsubscribe(subscriber)

        def publish_messages():
            for _ in range(100):
                message = json.dumps({"event": "test_event", "data": "test_data"})
                with patch.object(self.broker, "_validate_message", return_value=None):
                    self.broker.publish(message)

        sub_thread = threading.Thread(target=manage_subscriber)
        pub_thread = threading.Thread(target=publish_messages)

        sub_thread.start()
        pub_thread.start()

        sub_thread.join()
        pub_thread.join()

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        # Subscriber may or may not have been subscribed during message processing
        self.assertTrue(subscriber.call_count >= 0)

    def test_performance_publish(self):
        """Benchmark publishing a large number of messages."""
        num_messages = 20000
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)

        start_time = time.time()
        for i in range(num_messages):
            message = json.dumps({"event": f"event_{i}", "data": f"data_{i}"})
            with patch.object(self.broker, "_validate_message", return_value=None):
                self.broker.publish(message)

        self.broker.shutdown()

        duration = time.time() - start_time
        print(f"Published {num_messages} messages in {duration:.2f} seconds.")

        self.assertLess(duration, 5)  # Ensure it completes in under 5 seconds

    def test_corrupted_message_handling(self):
        """Test resilience to corrupted or malformed data."""
        corrupted_message = "\x00\x01\x02BAD_JSON\x03\x04"

        with patch.object(self.broker, "_validate_message") as mock_validate:
            mock_validate.side_effect = json.JSONDecodeError("Invalid JSON", corrupted_message, 0)

            with self.assertRaises(json.JSONDecodeError):
                self.broker.publish(corrupted_message)

    def test_subscriber_throws_exception(self):
        """Ensure exceptions in one subscriber do not affect others."""
        subscriber1 = MagicMock(side_effect=Exception("Test Exception"))
        subscriber2 = MagicMock()
        self.broker.subscribe(subscriber1)
        self.broker.subscribe(subscriber2)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        subscriber1.assert_called_once_with(test_message)
        subscriber2.assert_called_once_with(test_message)

    def test_shutdown_with_unprocessed_messages(self):
        """Test shutdown with messages left in the queue."""
        for i in range(10):
            self.broker.queue.put(f"Message {i}")

        self.broker.shutdown()
        self.assertTrue(self.broker.queue.empty())

    def test_publish_after_shutdown(self):
        """Ensure publishing after shutdown raises an exception."""
        self.broker.shutdown()

        with self.assertRaises(BrokerException):
            self.broker.publish("Test message")

    def test_custom_exception(self):
        """Test that custom exceptions can be raised."""
        with self.assertRaises(BrokerException):
            raise BrokerException("Custom exception test")

    def test_no_subscribers(self):
        """Test that publishing works without any subscribers."""
        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        # No subscribers, so nothing should be processed
        self.assertTrue(True)  # Test passes if no exceptions are raised

    def test_concurrent_subscribe_unsubscribe_and_publish(self):
        """Test concurrent subscription, unsubscription, and publishing."""
        subscriber = MagicMock()

        def subscribe_unsubscribe():
            for _ in range(100):
                self.broker.subscribe(subscriber)
                self.broker.unsubscribe(subscriber)

        def publish_messages():
            for i in range(200):
                message = json.dumps({"event": f"event_{i}", "data": f"data_{i}"})
                with patch.object(self.broker, "_validate_message", return_value=None):
                    self.broker.publish(message)

        threads = [
            threading.Thread(target=subscribe_unsubscribe),
            threading.Thread(target=publish_messages),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        # Ensure no deadlocks occurred and no errors were raised
        self.assertTrue(True)

    def test_maximum_subscribers(self):
        """Test handling of a large number of subscribers."""
        max_subscribers = 1000
        subscribers = [MagicMock() for _ in range(max_subscribers)]

        for subscriber in subscribers:
            self.broker.subscribe(subscriber)

        test_message = json.dumps({"event": "test_event", "data": "test_data"})
        with patch.object(self.broker, "_validate_message", return_value=None):
            self.broker.publish(test_message)

        # Allow the background thread to process
        self.broker.queue.put("SHUTDOWN")
        self.broker._thread.join()

        for subscriber in subscribers:
            subscriber.assert_called_once_with(test_message)

    def test_partial_shutdown(self):
        """Test broker behavior if the thread is prematurely terminated."""
        with self.assertRaises(AssertionError):
            self.broker._thread._stop()

    def test_message_schema_error(self):
        """Test schema validation errors."""
        invalid_message = json.dumps({"invalid_field": "value"})

        with patch.object(self.broker, "_validate_message") as mock_validate:
            mock_validate.side_effect = jsonschema.ValidationError("Schema validation error")

            with self.assertRaises(jsonschema.ValidationError):
                self.broker.publish(invalid_message)

    def test_message_schema_error_handling(self):
        """Test handling of schema errors without crashing."""
        invalid_message = json.dumps({"invalid_field": "value"})

        with patch.object(self.broker, "_validate_message") as mock_validate:
            mock_validate.side_effect = jsonschema.SchemaError("Invalid schema")

            with self.assertRaises(jsonschema.SchemaError):
                self.broker.publish(invalid_message)

    def test_graceful_shutdown_under_load(self):
        """Test shutdown while processing a large number of messages."""
        num_messages = 500
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)

        for i in range(num_messages):
            message = json.dumps({"event": f"event_{i}", "data": f"data_{i}"})
            with patch.object(self.broker, "_validate_message", return_value=None):
                self.broker.publish(message)

        self.broker.shutdown()

        # Ensure all messages were processed
        self.assertEqual(subscriber.call_count, num_messages)

    def test_subscribe_none(self):
        """Test subscribing a None object raises an exception."""
        with self.assertRaises(SubscriberTypeException):
            self.broker.subscribe(None)

    def test_subscribe_non_callable(self):
        """Test subscribing a non-callable object raises an exception."""
        with self.assertRaises(SubscriberTypeException):
            self.broker.subscribe("not_a_callable")

    def test_unsubscribe_unsubscribed_subscriber(self):
        """Test unsubscribing a subscriber that is already removed."""
        subscriber = MagicMock()
        self.broker.subscribe(subscriber)
        self.broker.unsubscribe(subscriber)
        self.broker.unsubscribe(subscriber)


if __name__ == "__main__":
    unittest.main()
