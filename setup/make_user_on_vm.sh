USERNAME=$1
if [ -z "$USERNAME" ]; then
  echo "Usage: $0 <username>"
  exit 1
fi
useradd -m -s /bin/bash $USERNAME
echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME
chmod 440 /etc/sudoers.d/$USERNAME
mkdir -p /home/$USERNAME/.ssh
cp /root/.ssh/authorized_keys /home/$USERNAME/.ssh/
chown -R $USERNAME:$USERNAME /home/$USERNAME/.ssh
chmod 700 /home/$USERNAME/.ssh
chmod 600 /home/$USERNAME/.ssh/authorized_keys
