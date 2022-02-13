
from launch_ros.actions import Node
import pickle
from .aws import AWS
from .scp import SCP_Client
from .vpn import VPN
from .command_builder import BashBuilder
from .dds_config_builder import CycloneConfigBuilder

import logging
import os

import shutil
def make_zip_file(dir_name, target_path):
    root_dir, workspace_name = os.path.split(dir_name)
    print(root_dir, workspace_name)
    return shutil.make_archive(base_dir = workspace_name,
                               root_dir = root_dir,
                               format = "zip",
                               base_name = target_path)

def start():
    launch_new_instance = True
    if launch_new_instance:
        aws_instance = AWS()
        aws_instance.create()
        ip = aws_instance.get_ip()
        key_path = aws_instance.get_ssh_key_path()
        print(ip, key_path)
        vpn = VPN(ip)
        vpn.make_wireguard_keypair()
    else:
        ip = "13.52.249.171"
        key_path = "/home/root/fog_ws/FogROSKEY905.pem"
        # Note that we don't need to make new keypair if we keep the old ones
        vpn = VPN(ip)

    scp = SCP_Client(ip, key_path)
    scp.connect()

    vpn.start()

    # configure VPN on the cloud
    scp.execute_cmd("sudo apt install -y wireguard unzip")
    scp.send_file("/tmp/fogros-aws.conf", "/tmp/fogros-aws.conf")
    scp.execute_cmd("sudo cp /tmp/fogros-aws.conf /etc/wireguard/wg0.conf && sudo chmod 600 /etc/wireguard/wg0.conf && sudo wg-quick up wg0")

    # configure DDS
    cyclone_builder = CycloneConfigBuilder(["10.0.0.2"])
    cyclone_builder.generate_config_file()
    scp.send_file("/tmp/cyclonedds.xml", "~/cyclonedds.xml")

    # configure ROS env
    workspace_path = "/home/root/fog_ws"
    zip_dst = "/tmp/ros_workspace"
    make_zip_file(workspace_path, zip_dst)
    scp.execute_cmd("echo removing old workspace")
    scp.execute_cmd("rm -rf ros_workspace.zip ros2_ws fog_ws")
    scp.send_file(zip_dst+".zip", "/home/ubuntu/")
    scp.execute_cmd("unzip -q /home/ubuntu/ros_workspace.zip")
    scp.execute_cmd("echo successfully extracted new workspace")
    scp.send_file("/tmp/to_cloud_nodes", "/tmp/to_cloud_nodes")

    cmd_builder = BashBuilder()
    cmd_builder.append("source /home/ubuntu/ros2_rolling/install/setup.bash")
    cmd_builder.append("cd /home/ubuntu/fog_ws && colcon build --merge-install")
    cmd_builder.append(". /home/ubuntu/fog_ws/install/setup.bash")
    cmd_builder.append(cyclone_builder.env_cmd)
    cmd_builder.append("ros2 launch fogros2 cloud.launch.py")
    print(cmd_builder.get())
    scp.execute_cmd(cmd_builder.get())


def main():
    import socket
    HOST = 'localhost'
    PORT = 65432
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        conn, addr = s.accept()
        with conn:
            print('Connected by', addr)
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                conn.sendall(b"ACK")
                start()


if __name__ == '__main__':
    main()