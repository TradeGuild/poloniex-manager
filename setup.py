from setuptools import setup

classifiers = [
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 2",
    "Topic :: Software Development :: Libraries",
]

setup(
    name='poloniex-manager',
    version='0.0.9',
    py_modules=['poloniex_manager', 'poloniex_listener'],
    url='https://github.com/gitguild/poloniex-manager',
    license='MIT',
    classifiers=classifiers,
    author='Ira Miller',
    author_email='ira@gitguild.com',
    description='Poloniex plugin for the trade manager platform.',
    setup_requires=['pytest-runner'],
    install_requires=[
        'sqlalchemy>=1.0.9',
        'trade_manager>=0.0.3',
        'tapp-config>=0.0.2',
        'tappmq', 'requests',
    ],
    tests_require=['pytest', 'pytest-cov'],
    entry_points="""
[console_scripts]
poloniexm = poloniex_manager:main
poloniexl = poloniex_listener:main
"""
)
