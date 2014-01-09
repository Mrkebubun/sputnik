#!/bin/sh


check_superuser()
{
    echo -n "Checking for root permissions... "
    if [ `id -u` -ne 0 ]
    then
        echo "failed."
        echo "This script must be run as root." 1>&2
        exit 1
    else
        echo "ok."
    fi
}

check_user()
{
    echo -n "Checking/adding user sputnik... "
    PASSWD=`cat /etc/passwd | grep ^sputnik: | cut -d: -f 6,7`
    if [ $? ]
    then
        if [ X$PASSWD = X"/srv/sputnik:/bin/false" ]
        then
            echo ok.
        else
            echo failed.
            echo "User sputnik exists but with incorrect home or shell." 1>&2
            exit 1
        fi
    else
        if /usr/sbin/adduser --quiet --system --group --home=/srv/sputnik sputnik 2>&1
        then
            echo "ok."
        else
            echo "failed."
            echo "Error: cannot create user sputnik." 1>&2
            exit 1
        fi
    fi
}

check_dpkg_dependency()
{
    /usr/bin/dpkg -s $1 > /dev/null 2>&1
}

install_dpkg_dependency()
{
    /usr/bin/apt-get -y install $1 
}

check_source_dependency()
{
    $1 check > /dev/null 2>&1
}

install_source_dependency()
{
    $1 install > /dev/null 2>&1
}

check_python_dependency()
{
    /usr/bin/pip freeze 2>/dev/null | grep $1 > /dev/null 2>&1
}

install_python_dependency()
{
    /usr/bin/pip install $1 > /dev/null 2>&1
}

check_dependencies()
{
    echo "Checking $1 dependencies..."
    DEPENDENCY_FILE=${1}-dependencies
    if [ ! -z "$DEBUG" ]
    then
        DEPENDENCY_FILE="$DEPENDENCY_FILE.debug"
    fi
    if [ -d $DEPENDENCY_FILE ]
    then
        DIR=1
        DEPENDENCIES=`ls $DEPENDENCY_FILE/*`
    else
        DEPENDENCIES=`cat $DEPENDENCY_FILE`
    fi
    for i in $DEPENDENCIES
    do
        if [ ! -z $DIR ]
        then
            PACKAGE_NAME=`echo $i | sed 's/.*\/\(.*\)/\1/'`
        else
            PACKAGE_NAME=$i
        fi
        if check_${1}_dependency $i
        then
            echo $PACKAGE_NAME installed.
        else
            echo -n "$PACKAGE_NAME not installed. Installing... "
            install_${1}_dependency $i
            if check_${1}_dependency $i
            then
                echo done.
            else
                echo failed.
                echo "Error: unable to install $PACKAGE_NAME." 1>&2
                exit 1
            fi
        fi
    done
}

if [ X$1 = X"debug" ]
then
    echo Installing debug version of sputnik to /srv/sputnik
    DEBUG="debug"
elif [ X$1 = X"deploy" ]
then
    echo Installing deploy version of sputnik to /srv/sputnik
else
    echo "usage: $0 [debug|deploy]"
    exit 1
fi

#install_tar
#install_config

check_superuser
check_user
check_dependencies dpkg
check_dependencies source
check_dependencies python

