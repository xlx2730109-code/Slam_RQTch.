set -x
P=<REDACTED-PASSWORD>
echo "===== PATCH Sophus so2.cpp ====="
cd ~/Sophus_src
sed -i 's/unit_complex_.real() = 1.;/unit_complex_ = Complexd(1., 0.);/' sophus/so2.cpp
sed -i '/unit_complex_.imag() = 0.;/d' sophus/so2.cpp
grep -n "Complexd(1." sophus/so2.cpp
echo "===== REBUILD Sophus ====="
cd ~/Sophus_src/build && make -j4 2>&1 | tail -12
echo "$P" | sudo -S make install 2>&1 | tail -3
ls -la ~/Sophus_src/build/libSophus.so && echo "SOPHUS_OK" || echo "SOPHUS_FAIL"
echo "===== catkin_make ====="
source /opt/ros/noetic/setup.bash
cd ~/livo2_ws && catkin_make -j4 2>&1 | tail -35
echo "===== RESULT ====="
(ls ~/livo2_ws/devel/lib/fast_livo/fastlio_mapping 2>/dev/null || ls ~/livo2_ws/devel/lib/fast_livo/ 2>/dev/null) && echo "FASTLIVO_OK" || echo "FASTLIVO_FAIL"
echo "===== ALL_DONE ====="
