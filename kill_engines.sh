#! /bin/bash
ps aux | grep engine | awk '{print $2}' | xargs -I {} sudo kill -9 {}
