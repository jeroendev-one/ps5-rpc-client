docker run -it --rm --name ps5-rpc-client ps5-rpc-client \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -e DISPLAY=$DISPLAY \
  -v $HOME/.Xauthority:/root/.Xauthority \
  --network="host" \
  -v ${XDG_RUNTIME_DIR}/discord-ipc-0:/tmp/discord-ipc-0
