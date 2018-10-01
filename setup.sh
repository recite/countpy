#!/usr/bin/env bash

# Check root
if [[ `id -u` -ne 0 ]]; then
	echo "Setup must be run as root user."
	exit 1
fi

# Setup vars
curdir=`pwd`
appdir=$(realpath "$(dirname $0)")
countpy_svc="/etc/systemd/system/countpy.service"
redis_svc="/etc/systemd/system/redis.service"
countpy_fqdn="countpy.com"
countpy_conf="/etc/nginx/sites-available/$countpy_fqdn"

# Install packages
packages=""
dpkg --list | grep build-essential &> /dev/null || packages="${packages} build-essential"
dpkg --list | grep python3.5 &> /dev/null || packages="${packages} python3.5"
dpkg --list | grep python3-dev &> /dev/null || packages="${packages} python3-dev"
dpkg --list | grep tcl &> /dev/null || packages="${packages} tcl"
dpkg --list | grep nodejs &> /dev/null || packages="${packages} nodejs"
dpkg --list | grep npm &> /dev/null || packages="${packages} npm"
dpkg --list | grep git-core &> /dev/null || packages="${packages} git-core"
dpkg --list | grep nginx &> /dev/null || packages="${packages} nginx"
if [[ ! -z "${packages}" ]]; then
    apt-get update && apt-get install -y ${packages}
fi

# Install pip
if ! which pip3 &> /dev/null; then
    cd /tmp
    curl -O https://bootstrap.pypa.io/get-pip.py
    python3 get-pip.py
    rm -f get-pip.py
    cd $curdir
else
    pip3 install pip --upgrade
fi

# Install python libraries
pip3 install -r $appdir/requirements.txt --upgrade
if ! which uwsgi &> /dev/null; then
    echo "uWSGI is not installed"
    exit 1
fi

# Install bower
if ! which bower &> /dev/null; then
    npm install -g bower
fi

# Backward compatibility for nodejs
[ -f /usr/bin/node ] || ln -s `which nodejs` /usr/bin/node

# Install static libraries
cd $appdir/app
bower install --allow-root
cd $curdir

# Install redis
if ! systemctl status redis &> /dev/null; then
    cd /tmp
    curl -O http://download.redis.io/redis-stable.tar.gz
    tar -xzvf redis-stable.tar.gz
    cd redis-stable
    make
    make test
    make install
    mkdir /etc/redis
    cp redis.conf /etc/redis
    sed -ri 's/^supervised .+/supervised systemd/g' /etc/redis/redis.conf
    sed -ri 's:^dir .+:dir /var/lib/redis:g' /etc/redis/redis.conf
    adduser --system --group --no-create-home redis
    mkdir /var/lib/redis
    chown redis:redis /var/lib/redis
    cat > $redis_svc <<EOF
[Unit]
Description=Redis In-Memory Data Store
After=network.target

[Service]
User=redis
Group=redis
ExecStart=/usr/local/bin/redis-server /etc/redis/redis.conf
ExecStop=/usr/local/bin/redis-cli shutdown
Restart=always

[Install]
WantedBy=multi-user.target
EOF
    cd $curdir
    rm -rf /tmp/redis-stable*

    grep vm.overcommit_memory /etc/sysctl.conf > /dev/null || \
    echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf

    grep net.core.somaxconn /etc/sysctl.conf > /dev/null || \
    echo "net.core.somaxconn = 65535" >> /etc/sysctl.conf

    sysctl -p

    systemctl daemon-reload
    systemctl enable redis
    systemctl start redis
fi

# Install countpy
if ! systemctl status countpy &> /dev/null; then
    adduser --system --group --no-create-home countpy
    chown -R countpy.www-data $appdir
    uwsgi_cmd=`which uwsgi`
    cat > $countpy_svc <<EOF
[Unit]
Description=uWSGI Server for countpy app
After=network.target

[Service]
User=countpy
Group=www-data
ExecStart=$uwsgi_cmd --ini $appdir/wsgi.ini
WorkingDirectory=$appdir
Restart=always
KillSignal=SIGTERM
Type=notify
StandardError=syslog
NotifyAccess=all

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable countpy
    systemctl start countpy
fi

# Configure nginx
[ -f /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default

if [ ! -f $countpy_conf ]; then
    cat > $countpy_conf <<EOF
server {
    listen 80;
    server_name $countpy_fqdn www.$countpy_fqdn;

    location /static {
        alias $appdir/static;
    }

    location / {
        include uwsgi_params;
        uwsgi_pass unix:///$appdir/countpy.sock;
    }
}
EOF

    ln -s $countpy_conf /etc/nginx/sites-enabled/$countpy_fqdn
fi

# Restart nginx
systemctl enable nginx
systemctl restart nginx

# Finished
echo "Done!"
