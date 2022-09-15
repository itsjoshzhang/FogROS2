# Copyright 2022 The Regents of the University of California (Regents)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright ©2022. The Regents of the University of California (Regents).
# All Rights Reserved. Permission to use, copy, modify, and distribute this
# software and its documentation for educational, research, and not-for-profit
# purposes, without fee and without a signed licensing agreement, is hereby
# granted, provided that the above copyright notice, this paragraph and the
# following two paragraphs appear in all copies, modifications, and
# distributions. Contact The Office of Technology Licensing, UC Berkeley, 2150
# Shattuck Avenue, Suite 510, Berkeley, CA 94720-1620, (510) 643-7201,
# otl@berkeley.edu, http://ipira.berkeley.edu/industry-info for commercial
# licensing opportunities. IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY
# FOR DIRECT, INDIRECT, SPECIAL, INCIDENTAL, OR CONSEQUENTIAL DAMAGES,
# INCLUDING LOST PROFITS, ARISING OUT OF THE USE OF THIS SOFTWARE AND ITS
# DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE. REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE. THE SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY,
# PROVIDED HEREUNDER IS PROVIDED "AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE
# MAINTENANCE, SUPPORT, UPDATES, ENHANCEMENTS, OR MODIFICATIONS.

import json
import os
import requests
from math import radians, cos, sin, asin, sqrt
from ping3 import ping

import boto3
from botocore.exceptions import ClientError

from .cloud_instance import CloudInstance
from .name_generator import get_unique_name


class AWSCloudInstance(CloudInstance):
    """AWS Implementation of CloudInstance."""

    def __init__(
        self,
        ec2_instance_type="t2.micro",
        regions={},
        disk_size=30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.cloud_service_provider = "AWS"

        self.region, self.aws_ami_image = self.pick_region_and_ami(regions)
        self.ec2_instance_type = ec2_instance_type
        self.ec2_instance_disk_size = disk_size  # GB

        # aws objects
        self.ec2_instance = None
        self.ec2_resource_manager = boto3.resource("ec2", self.region)
        self.ec2_boto3_client = boto3.client("ec2", self.region)

        # Check for name collision among other AWS instances
        cur_instances = self.ec2_boto3_client.describe_instances(
            Filters=[
                {
                    "Name": "instance.group-name",
                    "Values": ["FOGROS2_SECURITY_GROUP"],
                },
                {"Name": "tag:FogROS2-Name", "Values": [self._name]},
            ]
        )
        while len(cur_instances["Reservations"]) > 0:
            self._name = get_unique_name()
            cur_instances = self.ec2_boto3_client.describe_instances(
                Filters=[
                    {
                        "Name": "instance.group-name",
                        "Values": ["FOGROS2_SECURITY_GROUP"],
                    },
                    {"Name": "tag:FogROS2-Name", "Values": [self._name]},
                ]
            )
        self._working_dir = os.path.join(self._working_dir_base, self._name)
        os.makedirs(self._working_dir, exist_ok=True)

        # key & security group names
        self.ec2_security_group = "FOGROS2_SECURITY_GROUP"
        self.ec2_key_name = f"FogROS2KEY-{self._name}"
        self._ssh_key_path = os.path.join(
            self._working_dir, f"{self.ec2_key_name}.pem"
        )

        # Auto-delete key pair collision (since any instance using this key
        # pair would be terminated already, otherwise it would be found in
        # the previous collision check)
        self.ec2_boto3_client.delete_key_pair(KeyName=self.ec2_key_name)

        # after config
        self._ssh_key = None
        self.ec2_security_group_ids = None

        self.create()

    def pick_region_and_ami(self, regions):
        aws_regions = {
            "us-east-2": (40.4167, -82.9167),
            "us-east-1": (38.0339, -78.4860),
            "us-west-1": (37.7749, -122.4194),
            "us-west-2": (45.5200, -122.6819),
            "af-south-1": (-33.9249, 18.4241),
            "ap-east-1": (22.2800, 114.1588),
            "ap-southeast-3": (-6.2315, 106.8275),
            "ap-south-1": (19.0760, 72.8777),
            "ap-northeast-3": (34.6723, 135.4848),
            "ap-northeast-2": (37.5665, 126.9780),
            "ap-southeast-1": (1.3521, 103.8198),
            "ap-southeast-2": (-33.8688, 151.2093),
            "ap-northeast-1": (35.6895, 139.6917),
            "ca-central-1": (43.6532, -79.3832),
            "eu-central-1": (50.1147, 8.6821),
            "eu-west-1": (53.4129, -8.2439),
            "eu-west-2": (51.5074, -0.1278),
            "eu-south-1": (45.4642, 9.1900),
            "eu-west-3": (48.8566, 2.3522),
            "eu-north-1": (59.3293, 18.0686),
            "me-south-1": (26.0667, 50.5577),
            "me-central-1": (23.4241, 53.8478),
            "sa-east-1": (-23.5505, -46.6333),
        }
        ip = json.loads(requests.get("https://ip.seeip.org/jsonip?").text)["ip"]
        response = requests.get("https://geolocation-db.com/json/" + ip + "&position=true").json()
        lat = response["latitude"]
        long = response["longitude"]
        def haversine(lat1, lon1, lat2, lon2):
            lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1 
            dlat = lat2 - lat1 
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a)) 
            km = 6371 * c
            return km
        closest_region = min(regions, key=lambda region: haversine(aws_regions[region][0], aws_regions[region][1], lat, long))
        print(closest_region)
        return closest_region, regions[closest_region]["ami_image"]

    def create(self):
        self.logger.info(f"Creating new EC2 instance with name {self._name}")
        self.create_security_group()
        self.generate_key_pair()
        self.create_ec2_instance()
        self.info(flush_to_disk=True)
        self.test_latency()
        # self.connect()
        # self.install_ros()
        # self.install_cloud_dependencies()
        # self.install_colcon()
        # self.push_ros_workspace()
        # self.info(flush_to_disk=True)
        # self._is_created = True

    def test_latency(self):
        ping_sum = 0
        count = 0
        while count < 100:
            latency = ping(self._ip)
            if latency:
                ping_sum += latency
                count += 1
        print(ping_sum / count)

    def info(self, flush_to_disk=True):
        info_dict = super().info(flush_to_disk)
        info_dict["ec2_region"] = self.region
        info_dict["ec2_instance_type"] = self.ec2_instance_type
        info_dict["disk_size"] = self.ec2_instance_disk_size
        info_dict["aws_ami_image"] = self.aws_ami_image
        info_dict["ec2_instance_id"] = self.ec2_instance.instance_id
        if flush_to_disk:
            with open(os.path.join(self._working_dir, "info"), "w+") as f:
                json.dump(info_dict, f)
        return info_dict

    def get_default_vpc(self):
        response = self.ec2_boto3_client.describe_vpcs(
            Filters=[{"Name": "is-default", "Values": ["true"]}]
        )
        vpcs = response.get("Vpcs", [])

        if len(vpcs) == 0:
            self.logger.warn("No default VPC found.  Creating one.")
            response = self.ec2_boto3_client.create_default_vpc()
            vpc_id = response["Vpc"]["VpcId"]
            self.logger.warn(f"Created new default VPC {vpc_id}")
            return vpc_id

        if len(vpcs) > 1:
            # This shouldn't happen, but just in case, warn.
            self.logger.warn(
                "Multiple default VPCs.  This may lead to undefined behavior."
            )

        vpc_id = vpcs[0].get("VpcId", "")
        self.logger.info(f"Using VPC: {vpc_id}")
        return vpc_id

    def create_security_group(self):
        vpc_id = self.get_default_vpc()
        try:
            response = self.ec2_boto3_client.describe_security_groups(
                GroupNames=[self.ec2_security_group]
            )
            security_group_id = response["SecurityGroups"][0]["GroupId"]
        except ClientError as e:
            # check if the group does not exist. we'll create one in
            # that case.  Any other error is unexpected and re-thrown.
            if e.response["Error"]["Code"] != "InvalidGroup.NotFound":
                raise e

            self.logger.warn("Security group does not exist, creating.")
            response = self.ec2_boto3_client.create_security_group(
                GroupName=self.ec2_security_group,
                Description=(
                    "Security group used by FogROS 2 (safe to delete"
                    " when FogROS 2 is not in use)"
                ),
                VpcId=vpc_id,
            )
            security_group_id = response["GroupId"]
            self.logger.info(
                f"Security group {security_group_id} created in vpc {vpc_id}."
            )

            data = self.ec2_boto3_client.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "-1",
                        "FromPort": 0,
                        "ToPort": 65535,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    }
                ],
            )
            self.logger.info(f"Ingress Successfully Set {data}")

        self.logger.info(f"Using security group id: {security_group_id}")
        self.ec2_security_group_ids = [security_group_id]

    def generate_key_pair(self):
        ec2_keypair = self.ec2_boto3_client.create_key_pair(
            KeyName=self.ec2_key_name
        )
        self._ssh_key = ec2_keypair["KeyMaterial"]

        # Since we're writing an SSH key, make sure to write with
        # user-only permissions.
        with open(
            os.open(self._ssh_key_path, os.O_CREAT | os.O_WRONLY, 0o600), "w"
        ) as f:
            f.write(self._ssh_key)

    def create_ec2_instance(self):
        # start EC2 instance
        # note that we can start muliple instances at the same time
        instances = self.ec2_resource_manager.create_instances(
            ImageId=self.aws_ami_image,
            MinCount=1,
            MaxCount=1,
            InstanceType=self.ec2_instance_type,
            KeyName=self.ec2_key_name,
            SecurityGroupIds=self.ec2_security_group_ids,
            ClientToken=f"FogROS2-{self._name}",
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "FogROS2-Name", "Value": self._name}],
                }
            ],
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": self.ec2_instance_disk_size,
                        "VolumeType": "standard",
                    },
                }
            ],
        )

        self.ec2_instance = instances[0]

        # use the boto3 waiter
        self.logger.info("Waiting for launching to finish")
        self.ec2_instance.wait_until_running()

        # reload instance object until IP
        self.ec2_instance.reload()
        self._ip = self.ec2_instance.public_ip_address
        while not self._ip:
            self.ec2_instance.reload()
            self.logger.info("Waiting for launching to finish")
            self._ip = self.ec2_instance.public_ip_address
        self.logger.info(
            f"Created {self.ec2_instance_type} instance named {self._name} "
            f"with id {self.ec2_instance.id} and public IP address {self._ip}"
        )
