import io
import os
from pathlib import Path
from importlib import util

from setuptools import setup

NAMESPACE = 'ptn'
COMPONENT = 'missionalertbot'

here = Path().absolute()

# Bunch of things to allow us to dynamically load the metadata file in order to read the version number.
# This is really overkill but it is better code than opening, streaming and parsing the file ourselves.

metadata_name = f'{NAMESPACE}.{COMPONENT}._metadata'
spec = util.spec_from_file_location(metadata_name, os.path.join(here, NAMESPACE, COMPONENT, '_metadata.py'))
metadata = util.module_from_spec(spec)
spec.loader.exec_module(metadata)

# load up the description field
with io.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name=f'{NAMESPACE}.{COMPONENT}',
    version=metadata.__version__,
    packages=['ptn.missionalertbot', 'ptn.missionalertbot.botcommands', 'ptn.missionalertbot.database'],
    description='Pilots Trade Network Mission Alert Bot',
    long_description=long_description,
    author='Charles Tosh',
    url='',
    install_requires=[
        'discord.py',
        'python-dotenv',
    ],
    entry_points={
        'console_scripts': [
            'missionalertbot=ptn.missionalertbot.application:run',
        ],
    },
    license='None',
    keyworkd='PTN',
    project_urls={
        "Source": "https://github.com/PilotsTradeNetwork/MissionAlertBot",
    },
    python_required='>=3.8',
)
