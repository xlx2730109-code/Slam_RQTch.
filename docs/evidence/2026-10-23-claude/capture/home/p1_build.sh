set -x
P=<REDACTED-PASSWORD>
LOG(){ echo "===== $* ====="; }
LOG STAGE1 apt deps
echo "$P" | sudo -S apt-get install -y ros-noetic-image-transport ros-noetic-vision-opencv ros-noetic-cv-bridge 2>&1 | tail -5
LOG STAGE2 Sophus
cd ~ && rm -rf Sophus_src
git clone https://github.com/strasdat/Sophus.git Sophus_src 2>&1 | tail -2
cd ~/Sophus_src && git checkout a621ff2 2>&1 | tail -2
mkdir -p build && cd build && cmake .. -DBUILD_SOPHUS_TESTS=OFF -DBUILD_SOPHUS_EXAMPLES=OFF 2>&1 | tail -5 && make -j4 2>&1 | tail -8 && echo "$P" | sudo -S make install 2>&1 | tail -3
LOG STAGE3 vikit
cd ~/livo2_ws/src && rm -rf rpg_vikit && git clone https://github.com/xuankuzcr/rpg_vikit.git 2>&1 | tail -2
LOG STAGE4 catkin_make
source /opt/ros/noetic/setup.bash
cd ~/livo2_ws && catkin_make -j4 2>&1 | tail -40
LOG BUILD_RESULT
ls ~/livo2_ws/devel/lib/fast_livo/ 2>/dev/null && echo "FASTLIVO_BUILT_OK" || echo "FASTLIVO_BUILD_FAILED"
LOG ALL_DONE
