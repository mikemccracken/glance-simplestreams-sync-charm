#!/usr/bin/env python2.7
#
# Copyright 2014 Canonical Ltd.
#
# This file is part of the glance-simplestreams sync charm.

# The glance-simplestreams sync charm is free software: you can
# redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version.
#
# The charm is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this charm.  If not, see <http://www.gnu.org/licenses/>.

# This script runs as a cron job installed by the
# glance-simplestreams-sync juju charm.  It reads config files that
# are written by the hooks of that charm based on its config and
# juju relation to keystone. However, it does not execute in a
# juju hook context itself.

import atexit
from keystoneclient.v2_0 import client as keystone_client
import logging
import os
from simplestreams.mirrors import glance, UrlMirrorReader
from simplestreams.objectstores.swift import SwiftObjectStore
from simplestreams.util import read_signed, path_from_mirror_url
import sys
import yaml

KEYRING = '/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg'
CONF_FILE_DIR = '/etc/glance-simplestreams-sync'
MIRRORS_CONF_FILE_NAME = os.path.join(CONF_FILE_DIR, 'mirrors.yaml')
ID_CONF_FILE_NAME = os.path.join(CONF_FILE_DIR, 'identity.yaml')

SYNC_RUNNING_FLAG_FILE_NAME = os.path.join(CONF_FILE_DIR, 'sync-running.pid')

# juju looks in simplestreams/data/* in swift to figure out which
# images to deploy, so this path isn't really configurable even though
# it is.
SWIFT_DATA_DIR = 'simplestreams/data/'

PRODUCT_STREAMS_SERVICE_NAME = 'image-stream'
PRODUCT_STREAMS_SERVICE_TYPE = 'product-streams'
PRODUCT_STREAMS_SERVICE_DESC = 'Ubuntu Product Streams'

CRON_POLL_FILENAME = '/etc/cron.d/glance_simplestreams_sync_fastpoll'

# TODOs:
#   - We might want to allow people to set regions as well, so
#     you can have one charm sync to one region, instead of doing a cross
#     region sync.
#   - allow people to specify their own policy, since they can specify
#     their own mirrors.
#   - potentially allow people to specify backup mirrors?
#   - debug keyring support
#   - figure out what content_id is and whether we should allow users to
#     set it


def setup_logging():
    logfilename = '/var/log/glance-simplestreams-sync.log'
    h = logging.FileHandler(logfilename)
    h.setFormatter(logging.Formatter(
        '%(levelname)-9s * %(asctime)s [PID:%(process)d] * %(name)s * '
        '%(message)s',
        datefmt='%m-%d %H:%M:%S'))

    logger = logging.getLogger('')
    logger.setLevel('DEBUG')
    logger.addHandler(h)

    return logger


log = setup_logging()


def policy(content, path):
    if path.endswith('sjson'):
        return read_signed(content, keyring=KEYRING)
    else:
        return content


def read_conf(filename):
    with open(filename) as f:
        confobj = yaml.load(f)
    return confobj


def get_conf():
    conf_files = [ID_CONF_FILE_NAME, MIRRORS_CONF_FILE_NAME]
    for conf_file_name in conf_files:
        if not os.path.exists(conf_file_name):
            log.info("{} does not exist, exiting.".format(conf_file_name))
            sys.exit(1)

    id_conf = read_conf(ID_CONF_FILE_NAME)
    if None in id_conf.values():
        log.info("Configuration value missing in {}:\n"
                 "{}".format(ID_CONF_FILE_NAME, id_conf))
        sys.exit(1)
    mirrors = read_conf(MIRRORS_CONF_FILE_NAME)
    if None in mirrors.values():
        log.info("Configuration value missing in {}:\n"
                 "{}".format(MIRRORS_CONF_FILE_NAME, mirrors))
        sys.exit(1)

    return id_conf, mirrors


def set_openstack_env(id_conf):
    auth_url = '%s://%s:%s/v2.0' % (id_conf['auth_protocol'],
                                    id_conf['auth_host'],
                                    id_conf['auth_port'])
    os.environ['OS_AUTH_URL'] = auth_url
    os.environ['OS_USERNAME'] = id_conf['admin_user']
    os.environ['OS_PASSWORD'] = id_conf['admin_password']
    os.environ['OS_TENANT_ID'] = id_conf['admin_tenant_id']


def do_sync(mirrors):

    for mirror_info in mirrors['mirror_list']:
        mirror_url, initial_path = path_from_mirror_url(mirror_info['url'],
                                                        mirror_info['path'])

        log.info("configuring sync for url {}".format(mirror_info))

        smirror = UrlMirrorReader(mirror_url, policy=policy)

        store = SwiftObjectStore(SWIFT_DATA_DIR)

        config = {'max_items': mirror_info['max'],
                  'keep': False,
                  'content_id': 'auto.sync'}

        tmirror = glance.GlanceMirror(config=config, objectstore=store)
        log.info("calling GlanceMirror.sync")
        tmirror.sync(smirror, path=initial_path)


def create_product_streams_service(ksc):

    swift_endpoints = [e._info for e in ksc.endpoints.list()
                       if e._info['name'] == 'swift']
    if len(swift_endpoints) != 1:
        log.warning("found %d swift endpoints, expecting one - not"
                    " creating product-streams.".format(len(swift_endpoints)))
        return

    swift_endpoint = swift_endpoints[0]

    ps_services = [s._info for s in ksc.services.list()
                   if s._info['name'] == PRODUCT_STREAMS_SERVICE_NAME]
    if len(ps_services) != 1:
        log.warning("found %d product-streams services. expecting one."
                    " - not creating new endpoint.".format(len(ps_services)))
        return

    ps_service_id = ps_services[0]['service_id']

    ksc.endpoints.create(region=swift_endpoint['region'],
                         service_id=ps_service_id,
                         publicurl=swift_endpoint['publicurl'],
                         adminurl=swift_endpoint['adminurl'],
                         internalurl=swift_endpoint['internalurl'])


def cleanup():
    try:
        os.unlink(SYNC_RUNNING_FLAG_FILE_NAME)
    except OSError as e:
        if e.errno != 2:
            raise e

atexit.register(cleanup)

if __name__ == "__main__":

    if os.path.exists(SYNC_RUNNING_FLAG_FILE_NAME):
        log.info("sync started while pidfile exists, exiting")
        sys.exit(0)

    with open(SYNC_RUNNING_FLAG_FILE_NAME, 'w') as f:
        f.write(str(os.getpid()))

    id_conf, mirrors = get_conf()

    set_openstack_env(id_conf)

    ksc = keystone_client.Client(username=os.environ['OS_USERNAME'],
                                 password=os.environ['OS_PASSWORD'],
                                 tenant_id=os.environ['OS_TENANT_ID'],
                                 auth_url=os.environ['OS_AUTH_URL'])

    servicenames = [s._info['name'] for s in ksc.services.list()]
    ps_service_exists = PRODUCT_STREAMS_SERVICE_NAME in servicenames
    swift_exists = 'swift' in servicenames

    if not ps_service_exists and id_conf['use_swift'] and swift_exists:
        create_product_streams_service(ksc)

    try:
        do_sync(mirrors)
    except Exception as e:
        log.exception("Exception during do_sync")
        log.error("Errors in sync, not changing cron frequency.")
        return

    os.unlink(CRON_POLL_FILENAME)
    log.info("Sync successful. Every-minute cron job removed.")
