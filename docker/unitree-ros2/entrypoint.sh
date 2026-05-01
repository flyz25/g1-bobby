#!/usr/bin/env bash
set -euo pipefail

set +u
source /opt/ros/humble/setup.bash

if [ -f /opt/unitree/unitree_ros2/cyclonedds_ws/install/setup.bash ]; then
  source /opt/unitree/unitree_ros2/cyclonedds_ws/install/setup.bash
fi
set -u

export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
export G1_BOBBY_UNITREE_DDS_INTERFACE="${G1_BOBBY_UNITREE_DDS_INTERFACE:-lo}"

if [ -z "${CYCLONEDDS_URI:-}" ]; then
  cat > /tmp/g1-bobby-cyclonedds.xml <<XML
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS>
  <Domain>
    <General>
      <Interfaces>
        <NetworkInterface name="${G1_BOBBY_UNITREE_DDS_INTERFACE}" />
      </Interfaces>
      <AllowMulticast>true</AllowMulticast>
    </General>
  </Domain>
</CycloneDDS>
XML
  export CYCLONEDDS_URI="file:///tmp/g1-bobby-cyclonedds.xml"
fi

exec "$@"
