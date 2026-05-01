FROM ros:humble-ros-base-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
    CYCLONEDDS_HOME=/opt/cyclonedds/install \
    LD_LIBRARY_PATH=/opt/cyclonedds/install/lib \
    MUJOCO_HOME=/opt/mujoco/mujoco-3.3.6 \
    UNITREE_MUJOCO_HOME=/opt/unitree/unitree_mujoco \
    PYTHONPATH=/workspace/g1-bobby/apps/unitree_bridge:/workspace/g1-bobby/packages/contracts

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG UNITREE_ROS2_REPO=https://github.com/unitreerobotics/unitree_ros2.git
ARG UNITREE_ROS2_REF=master
ARG UNITREE_SDK2_REPO=https://github.com/unitreerobotics/unitree_sdk2.git
ARG UNITREE_SDK2_REF=main
ARG UNITREE_SDK2_PYTHON_REPO=https://github.com/unitreerobotics/unitree_sdk2_python.git
ARG UNITREE_SDK2_PYTHON_REF=master
ARG UNITREE_MUJOCO_REPO=https://github.com/unitreerobotics/unitree_mujoco.git
ARG UNITREE_MUJOCO_REF=main
ARG CYCLONEDDS_REF=releases/0.10.x
ARG MUJOCO_VERSION=3.3.6

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    g++ \
    git \
    libboost-all-dev \
    libeigen3-dev \
    libfmt-dev \
    libgl1 \
    libgl1-mesa-dri \
    libglfw3-dev \
    libspdlog-dev \
    libssl-dev \
    libyaml-cpp-dev \
    python3-colcon-common-extensions \
    python3-pip \
    python3-setuptools \
    python3-venv \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-rosidl-default-generators \
    tar \
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

RUN git clone --depth 1 --branch "${UNITREE_SDK2_REF}" "${UNITREE_SDK2_REPO}" unitree_sdk2 \
    && cmake -S /opt/unitree/unitree_sdk2 -B /opt/unitree/unitree_sdk2/build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/unitree_robotics \
      -DBUILD_EXAMPLES=OFF \
    && cmake --build /opt/unitree/unitree_sdk2/build --target install --parallel "$(nproc)"

RUN mkdir -p /opt/mujoco \
    && curl -fsSL \
      "https://github.com/google-deepmind/mujoco/releases/download/${MUJOCO_VERSION}/mujoco-${MUJOCO_VERSION}-linux-x86_64.tar.gz" \
      -o /tmp/mujoco.tar.gz \
    && tar -xzf /tmp/mujoco.tar.gz -C /opt/mujoco \
    && rm /tmp/mujoco.tar.gz

RUN git clone --depth 1 --branch "${UNITREE_MUJOCO_REF}" "${UNITREE_MUJOCO_REPO}" unitree_mujoco \
    && ln -s "/opt/mujoco/mujoco-${MUJOCO_VERSION}" /opt/unitree/unitree_mujoco/simulate/mujoco \
    && cmake -S /opt/unitree/unitree_mujoco/simulate \
      -B /opt/unitree/unitree_mujoco/simulate/build \
      -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /opt/unitree/unitree_mujoco/simulate/build --parallel "$(nproc)"

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
COPY packages/contracts ./packages/contracts
RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'python3 -m g1_bobby_unitree_bridge.main "$@"' \
    > /usr/local/bin/g1-bobby-unitree-probe \
    && chmod +x /usr/local/bin/g1-bobby-unitree-probe

RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'python3 -m g1_bobby_unitree_bridge.listener "$@"' \
    > /usr/local/bin/g1-bobby-unitree-listen \
    && chmod +x /usr/local/bin/g1-bobby-unitree-listen

RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'python3 -m g1_bobby_unitree_bridge.command_dry_run "$@"' \
    > /usr/local/bin/g1-bobby-unitree-command-dry-run \
    && chmod +x /usr/local/bin/g1-bobby-unitree-command-dry-run

RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'python3 -m g1_bobby_unitree_bridge.sim "$@"' \
    > /usr/local/bin/g1-bobby-unitree-sim \
    && chmod +x /usr/local/bin/g1-bobby-unitree-sim

COPY docker/unitree-ros2/entrypoint.sh /usr/local/bin/g1-bobby-unitree-entrypoint
RUN chmod +x /usr/local/bin/g1-bobby-unitree-entrypoint

ENTRYPOINT ["g1-bobby-unitree-entrypoint"]
CMD ["g1-bobby-unitree-probe"]
