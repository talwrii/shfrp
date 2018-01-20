
import sys
try:
    # setuptools entry point is slow
    #  if we have festentrypoint use
    #  a fast entry point
    import fastentrypoints
except ImportError:
    sys.stdout.write('Not using fastentrypoints\n')
    pass


import setuptools
import os

HERE = os.path.dirname(__file__)

setuptools.setup(
    name='shfrp',
    version="0.1.0",
    author='Tal Wrii',
    author_email='talwrii@gmail.com',
    description='',
    license='GPLv3',
    keywords='',
    url='',
    packages=['shfrp'],
    long_description='See https://github.com/talwrii/shfrp',
    entry_points={
        'console_scripts': [
            'shfrp=shfrp.shfrp:main',
            'shfrpgui=shfrp.shfrpgui:main'
        ]
    },
    classifiers=[
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)"
    ],
    test_suite='nose.collector',
    install_requires=['xerox']
)
