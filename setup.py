from setuptools import setup, find_packages

setup(
    name="nse-trading-bot",
    version="2.0.0",
    packages=find_packages(where="backend"),
    package_dir={"": "backend"},
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "websockets>=12.0",
        "pydantic>=2.5.3",
        "pandas>=2.1.4",
        "numpy>=1.26.3",
        "ta>=0.11.0",
    ],
    extras_require={
        "broker": ["fyers-apiv3>=3.0.0"],
        "dev": ["pytest>=7.4.0", "black>=23.0.0", "mypy>=1.7.0"],
    },
    python_requires=">=3.10",
)