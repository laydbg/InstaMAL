from setuptools import setup, find_packages

setup(
    name='instamal',
    version='0.1.0',
    packages=find_packages(where="src"),
    package_dir={'': 'src'},
    entry_points={
        'console_scripts': [
            'instamal = instamal.__main__:main',
        ],
    },
    install_requires=[
        "antlr4-python3-runtime==4.13.2",
        "mal-toolbox",
    ],
)
