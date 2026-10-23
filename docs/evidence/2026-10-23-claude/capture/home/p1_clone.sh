set -e
mkdir -p ~/livo2_ws/src
cd ~/livo2_ws/src
rm -rf FAST-LIVO2
for i in 1 2 3; do
  git clone https://github.com/hku-mars/FAST-LIVO2.git && break
  echo "retry $i"; sleep 3
done
echo "=== CLONE DONE ==="
echo "=== README dependency section ==="
sed -n '1,160p' FAST-LIVO2/README.md | grep -inE "depend|sophus|vikit|pcl|eigen|opencv|livox|mavros|commit|git clone|catkin|build" || true
echo "=== package.xml deps ==="
cat FAST-LIVO2/package.xml 2>/dev/null | grep -iE "depend"
echo "=== tree ==="
ls FAST-LIVO2
echo "=== ALL DONE ==="
