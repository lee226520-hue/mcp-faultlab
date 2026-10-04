from setuptools import find_packages, setup


setup(
    name="mcp-faultlab",
    version="0.2.0",
    description="Deterministic failure testing for MCP tools and AI agents.",
    packages=find_packages(include=["mcp_faultlab", "mcp_faultlab.*"]),
    python_requires=">=3.9",
    entry_points={"console_scripts": ["mcp-faultlab=mcp_faultlab.cli:main"]},
)

