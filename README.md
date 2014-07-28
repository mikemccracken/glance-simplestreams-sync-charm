# Overview

This charm provides a service that syncs your OpenStack cloud's
available OS images in OpenStack Glance with the available images from
a set of simplestreams mirrors, by default using
cloud-images.ubuntu.com.

It will create a user named 'image-stream' in the 'services' tenant.
If swift is enabled, glance will store its images in swift using the
image-stream username.

It can optionally also store simplestreams metadata into Swift for
future use by juju. If enabled, it publishes the URL for that metadata
as the endpoints of a new OpenStack service called 'product-streams'.
If using Swift is not enabled, the product-streams service will still
exist, but nothing will respond to requests to its endpoints.

The charm installs a cron job that repeatedly checks the
status of related services and begins syncing image data from your
configured mirrors as soon as all services are in place.

It can be deployed at any time, and upon deploy (or changing the 'run'
config setting), it will attempt to contact keystone and glance and
start a sync every minute until a successful sync occurs.

The charm can optionally also send sync transfer status messages via a
rabbitmq exchange, if it is provided with an amqp relation to a
rabbitmq-server charm.

# Requirements

This charm requires a juju relation to Keystone. It also requires a
running Glance instance, but not a relation - it connects with glance
via its endpoint as published in Keystone.

# Usage

    juju deploy glance-simplestreams-sync [--config optional-config.yaml]
    juju add-relation keystone glance-simplestreams-sync

    # optional:
    juju add-relation rabbitmq-server glance-simplestreams-sync

# Configuration

The charm has the following configuration variables, in alphabetical order

## `cloud_name`

Cloud name to be used in simplestreams index file.

Default is 'glance-simplestreams-sync-openstack'.

## `content_id_template`

A Python-style .format() template to use when generating
content_id properties for images uploaded to glance.

The content_id is considered when matching images between the
source and destination to decide which images to mirror.  By
varying this value you can mirror disjoint sets of images from
the same source into a single glance, either by using multiple
deployments of this charm, or by using a tool such as
sstream-mirror-glance, and they will not interfere with each
other.

Here is a more interesting example value:

    com.example.customstack.{region}:ubuntu:celery-worker

Currently the only available substitution is "region".  Any
other attempted substitutions will break the sync script.


## `frequency`

`frequency` is a string, and must be one of 'hourly', 'daily',
'weekly'.  It controls how often the sync cron job is run - it is used
to link the script into `/etc/cron.$frequency`.

## `mirror_list`

`mirror_list` is a yaml-formatted list of options to be passed to
Simplestreams. It defaults to settings for downloading images from
cloud-images.ubuntu.com, and is not yet tested with other mirror
locations. If you have set up your own Simplestreams mirror, you
should be able to set the necessary configuration values.

## `name_prefix`

Prefixed to object name when uploading to glance.

default: `auto-sync/`

## `region`

`region` is the OpenStack region in which the product-streams endpoint
will be created.

## `run`

`run` is a boolean that enables or disables the sync cron script.  It
is True by default, and changing it from False to True will schedule
an immediate attempt to sync images.

## `use_swift`

`use_swift` is a boolean that determines whether or not to store data
in swift and publish the path to product metadata via the
'product-streams' endpoint.

*NOTE* Changing the value will only affect the next sync, and does not
 currently remove an existing product-streams service or delete
 potentially stale product data.


# Copyright

The glance-simplestreams sync charm is free software: you can
redistribute it and/or modify it under the terms of the GNU Affero General
Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

The charm is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this charm.  If not, see <http://www.gnu.org/licenses/>.
