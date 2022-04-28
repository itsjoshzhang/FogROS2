import json
import os
import shutil

from ros2cli.verb import VerbExtension

from fogros2 import AWS
from fogros2.util import instance_dir

class DeleteVerb(VerbExtension):
    def add_arguments(self, parser, cli_name):
        parser.add_argument(
            "--all", "-A", action="store_true", default=False, help="Delete All existing FogROS instances"
        )
        parser.add_argument("--name", "-n", type=str, nargs=1, help="Select FogROS instance name to delete")

    def delete_instance(self, instance):
        pwd = os.path.join(instance_dir(), instance)
        info_path = os.path.join(pwd, "info")
        if not os.path.isfile(info_path):
            print("the info file does not exist, likely that the instance is not fully initialized")
            return 
        with open(os.path.join(pwd, "info")) as f:
            instance_info = json.loads(f.read())

        if instance_info["cloud_service_provider"] == "AWS":
            print("Terminating EC2 instance")
            try:
                AWS.delete(instance_info["ec2_instance_id"], instance_info["ec2_region"])
            except:
                print(f"the instance {instance} does not exist")

        print("Removing Instance Dir")
        shutil.rmtree(pwd)

        print(f"Delete {instance} successfully!")

    def main(self, *, args):
        if args.all == True:
            instances = os.listdir(instance_dir())
            for instance in instances:
                print("======" + instance + "======")
                self.delete_instance(instance)
        else:
            self.delete_instance(args.name[0])
