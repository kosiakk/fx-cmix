#!/bin/bash
# Provision a GCE VM to run fx-cmix ablation variants.
#
# Installs the Google Cloud Ops Agent (so CPU/memory/disk of these long runs is
# visible in Cloud Monitoring), the clang-17 toolchain the makefile expects,
# then clones the repo and fetches enwik8.
#
# Debian 12 ships clang 13-16 and 19 but not 17, so clang-17 comes from
# apt.llvm.org. Matching the compiler keeps results comparable with the runs
# done elsewhere.
set -euo pipefail

echo "=== Ops Agent ==="
if ! systemctl is-active --quiet google-cloud-ops-agent 2>/dev/null; then
  curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
  sudo bash add-google-cloud-ops-agent-repo.sh --also-install
  rm -f add-google-cloud-ops-agent-repo.sh
fi
systemctl is-active google-cloud-ops-agent || true

echo "=== toolchain ==="
sudo apt-get update -qq
sudo apt-get install -y -qq wget gnupg lsb-release git make unzip upx-ucl curl >/dev/null 2>&1
if ! command -v clang++-17 >/dev/null; then
  wget -qO- https://apt.llvm.org/llvm-snapshot.gpg.key \
    | sudo tee /etc/apt/trusted.gpg.d/apt.llvm.org.asc >/dev/null
  echo 'deb http://apt.llvm.org/bookworm/ llvm-toolchain-bookworm-17 main' \
    | sudo tee /etc/apt/sources.list.d/llvm17.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq clang-17 llvm-17 >/dev/null 2>&1
fi
clang++-17 --version | head -1
llvm-profdata-17 --version | head -2 | tail -1

echo "=== repo ==="
[ -d "$HOME/fx-cmix" ] || git clone -q https://github.com/kosiakk/fx-cmix.git "$HOME/fx-cmix"
cd "$HOME/fx-cmix" && git pull -q origin main
git log --oneline -1

echo "=== corpus ==="
cd experiments/ablation && ./fetch_corpora.sh full >/dev/null 2>&1
ls -l corpora/enwik8

echo "=== ready ==="
nproc; free -g | awk '/Mem:/{print "RAM_GB="$2}'; df -h / | tail -1
