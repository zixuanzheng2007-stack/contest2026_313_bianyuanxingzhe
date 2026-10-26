set -e
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y git curl ca-certificates python3 python-is-python3
mkdir -p ~/bin
curl -fsSL https://raw.githubusercontent.com/GerritCodeReview/git-repo/v2.66/repo -o ~/bin/repo || \
  curl -fsSL https://cdn.jsdelivr.net/gh/GerritCodeReview/git-repo@v2.66/repo -o ~/bin/repo
chmod +x ~/bin/repo
# fallback copy from host share if needed later
echo "export PATH=\"\$HOME/bin:\$PATH\"" >> ~/.bashrc
export PATH="$HOME/bin:$PATH"
git --version
python3 --version
~/bin/repo --version || python3 ~/bin/repo --version || true
whoami