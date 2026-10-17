FROM osrf/ros:noetic-desktop-full@sha256:7dbfb9576d8e6d226c31e06129a82aaab8702695f38eca2116918cb9b9308797
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential ca-certificates cmake git patch python3-pip python3-numpy     libatlas-base-dev libboost-all-dev libceres-dev libcgal-dev libeigen3-dev     libflann-dev libgflags-dev libgoogle-glog-dev libgsl-dev libhdf5-dev liblz4-dev     libopencv-dev libopenmpi-dev libopenni-dev libopenni2-dev libqt5opengl5-dev     libsuitesparse-dev libvtk7-dev libvtk7-qt-dev libyaml-cpp-dev     opencl-c-headers ocl-icd-opencl-dev openmpi-bin qtbase5-dev freeglut3-dev     libgl-dev libglew-dev libglfw3-dev libglm-dev libglu1-mesa-dev libtbb-dev     libxkbcommon-x11-dev ros-noetic-lvr2 ros-noetic-mesh-msgs     ros-noetic-mesh-msgs-conversions ros-noetic-pcl-ros ros-noetic-cv-bridge     ros-noetic-image-transport ros-noetic-tf ros-noetic-rosbag     ros-noetic-eigen-conversions ros-noetic-message-filters     && rm -rf /var/lib/apt/lists/*
ARG METHOD
COPY build_ros.py /opt/build_ros.py
RUN python3 /opt/build_ros.py dependencies "$METHOD"
COPY source /opt/source
COPY patches /opt/patches
COPY build-input.json /opt/build-input.json
RUN python3 /opt/build_ros.py method "$METHOD"
COPY inventory.py /opt/inventory.py
RUN python3 /opt/inventory.py > /opt/environment.json
ENV RIMBA_EXTERNAL_WORKSPACE=/opt/workspace
ENTRYPOINT []
