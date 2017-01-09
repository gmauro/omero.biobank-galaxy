#!/bin/bash

source /galaxy-central/.venv/bin/activate

export PYTHONPATH=/galaxy-central/lib/:/galaxy-central/.venv/local/lib/python2.7/site-packages/:/usr/lib/python2.7/dist-packages/ 

cd /galaxy-central/scripts/tools

python ajax_dynamic_options.py /etc/galaxy/galaxy.ini

