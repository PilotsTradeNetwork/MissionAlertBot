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
    packages=[
        'ptn.missionalertbot', # core
        'ptn.missionalertbot.botcommands', # user interactions
        'ptn.missionalertbot.classes', # classes
        'ptn.missionalertbot.database', # database
        'ptn.missionalertbot.modules', # modules
        'ptn.missionalertbot.resources' # default images and fonts
        ],
    description='Pilots Trade Network Mission Alert Bot',
    long_description=long_description,
    author='Charlie Tosh',
    url='',
    install_requires=[
        # 'aiohttp==3.7.4.post0',
        'async-timeout==3.0.1',
        # 'attrs==20.3.0',
        # 'chardet==4.0.0',
        'DateTime==4.3',
        'discord==1.0.1',
        'discord.py>=2.3.0',
        # 'idna==3.1',
        # 'multidict==5.1.0',
        'Pillow==10.2.0',
        'python-dotenv==0.15.0',
        # 'pytz==2021.1',
        'typing-extensions==3.7.4.3',
        # 'yarl==1.6.3',
        # 'zope.interface==5.2.0',
        # 'update-checker==0.18.0',
        # 'aiofiles==0.6.0',
        'asyncpraw==7.7.0',
        'asyncprawcore==2.3.0',
        'python-dateutil>=2.8.1',
        'emoji>=2.2.0',
        'bs4>=0.0.1',
        'texttable>=1.6.4'
    ],
    entry_points={
        'console_scripts': [
            'missionalertbot=ptn.missionalertbot.application:run',
        ],
    },
    license='None',
    keyword='PTN',
    project_urls={
        "Source": "https://github.com/PilotsTradeNetwork/MissionAlertBot",
    },
    python_required='>=3.9',
)
