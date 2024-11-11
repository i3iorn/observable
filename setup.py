from setuptools import setup, find_packages

setup(
    name='observable-framework',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
    ],
    extras_require={
    },
    author='Björn Schrammel',
    author_email='bjorn@schrammel.dev',
    description='An easy to use observable framework for Python',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/i3iorn/observable-framework',
    classifiers=[
        'Programming Language :: Python :: 3.9',
        'License :: OSI Approved :: MIT License',
    ],
)
