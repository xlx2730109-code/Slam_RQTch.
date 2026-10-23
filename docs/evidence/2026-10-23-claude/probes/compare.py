import hashlib, os, sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.abspath(__file__))
REPO = r"E:/HuanCun/Desktop/阮老师_消防/Slam_RQTch/docs/source/jiaoda"


def h(p):
    b = open(p, "rb").read()
    try:
        b = b.decode("utf-8").replace("\r\n", "\n").encode()
    except UnicodeDecodeError:
        pass
    return hashlib.sha256(b).hexdigest()


remote = {}
for line in open(os.path.join(BASE, "remote_jiaoda_sha.txt"), encoding="utf-8"):
    s, p = line.rstrip("\n").split("  ", 1)
    remote[p[2:]] = s

same, diff, only_r = [], [], []
for p, s in remote.items():
    lp = os.path.join(REPO, p)
    if not os.path.exists(lp):
        only_r.append(p)
    elif h(lp) == s:
        same.append(p)
    else:
        diff.append(p)

only_l = []
for root, _, fs in os.walk(REPO):
    for f in fs:
        rel = os.path.relpath(os.path.join(root, f), REPO).replace(os.sep, "/")
        if rel not in remote:
            only_l.append(rel)

print("remote", len(remote), "identical", len(same), "differ", len(diff),
      "only-jetson", len(only_r), "only-repo", len(only_l))
print("\n[DIFFER]", *sorted(diff), sep="\n  ")
print("\n[ONLY ON JETSON]", *sorted(only_r), sep="\n  ")
print("\n[ONLY IN REPO]", *sorted(only_l), sep="\n  ")
