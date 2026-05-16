from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="codeviewcli",
    version="2.0.0",
    author="CodeView CLI",
    description="A feature-rich CLI tool to view, edit, and fetch code with syntax highlighting",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "rich>=13.0.0",
        "pygments>=2.15.0",
        "textual>=0.50.0",
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "pathspec>=0.11.0",
        'windows-curses>=2.3.0; sys_platform == "win32"',
        "pyperclip>=1.8.0",
    ],
    entry_points={
        "console_scripts": [
            "codeview=codeviewcli.main:main",
            "cv=codeviewcli.main:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
