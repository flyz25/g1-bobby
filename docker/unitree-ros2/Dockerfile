FROM ros:humble-ros-base-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    CYCLONEDDS_HOME=/opt/cyclonedds/install \
    LD_LIBRARY_PATH=/opt/cyclonedds/install/lib \
    PYTHONPATH=/workspace/g1-bobby/apps/unitree_bridge

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG UNITREE_ROS2_REPO=https://github.com/unitreerobotics/unitree_ros2.git
ARG UNITREE_ROS2_REF=master
ARG UNITREE_SDK2_PYTHON_REPO=https://github.com/unitreerobotics/unitree_sdk2_python.git
ARG UNITREE_SDK2_PYTHON_REF=master
ARG CYCLONEDDS_REF=releases/0.10.x

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    git \
    libssl-dev \
    libyaml-cpp-dev \
    python3-colcon-common-extensions \
    python3-pip \
    python3-venv \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-rosidl-default-generators \
    && (apt-get install -y --no-install-recommends ros-humble-rosidl-generator-dds-idl || true) \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone --depth 1 --branch "${CYCLONEDDS_REF}" \
    https://github.com/eclipse-cyclonedds/cyclonedds.git cyclonedds \
    && cmake -S /opt/cyclonedds -B /opt/cyclonedds/build \
      -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds/install \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /opt/cyclonedds/build --target install --parallel "$(nproc)"

WORKDIR /opt/unitree

RUN git clone --depth 1 --branch "${UNITREE_ROS2_REF}" "${UNITREE_ROS2_REPO}" unitree_ros2 \
    && git clone --depth 1 --branch "${UNITREE_SDK2_PYTHON_REF}" \
      "${UNITREE_SDK2_PYTHON_REPO}" unitree_sdk2_python

RUN source /opt/ros/humble/setup.bash \
    && if [ -d /opt/unitree/unitree_ros2/cyclonedds_ws ]; then \
      cd /opt/unitree/unitree_ros2/cyclonedds_ws \
      && colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release; \
    fi

RUN python3 -m pip install --no-cache-dir --upgrade "pip<26" "setuptools<80" wheel \
    && python3 -m pip install --no-cache-dir cyclonedds==0.10.2 numpy opencv-python-headless \
    && python3 -m pip install --no-cache-dir --no-deps -e /opt/unitree/unitree_sdk2_python

WORKDIR /workspace/g1-bobby

COPY apps/unitree_bridge ./apps/unitree_bridge
RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'python3 -m g1_bobby_unitree_bridge.main "$@"' \
    > /usr/local/bin/g1-bobby-unitree-probe \
    && chmod +x /usr/local/bin/g1-bobby-unitree-probe

COPY docker/unitree-ros2/entrypoint.sh /usr/local/bin/g1-bobby-unitree-entrypoint
RUN chmod +x /usr/local/bin/g1-bobby-unitree-entrypoint

ENTRYPOINT ["g1-bobby-unitree-entrypoint"]
CMD ["g1-bobby-unitree-probe"]
