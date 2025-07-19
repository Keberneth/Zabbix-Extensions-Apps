#!/bin/bash

# List of networks to treat as internal
INTERNAL="0.0.0.0/0"

# Internal IP's to filter expression
INTERNAL_FILTER="src = "$(\
echo $INTERNAL \
  | sed -E 's/ / or src = /g' \
)

# Grab all ports we are listening to
LISTENPORTS=$(\
ss -4 --listen --numeric --no-header \
  | sed -E 's/.*[0-9.]+(%[^:]+)?:([0-9]+)\s.*/\2/' \
  | sort --unique --numeric-sort)

# | sed -E 's/.*[0-9.]+:([0-9]+)\s.*/\1/' \
# Convert ports to filter expression for ss
LISTEN=$(\
  echo "$LISTENPORTS" \
  | (readarray -t ARRAY; IFS=';'; echo "${ARRAY[*]}") \
  | sed -E 's/;/ or src = :/g')

# Output list of open ports
LISTENJSON=$(\
  echo "$LISTENPORTS" \
    | column --table \
              --table-columns port \
              --table-name openports \
              --table-noheadings \
              --json \
    | sed '1d;$d' \
  );

echo "{"

if [ -z "$LISTENJSON" ]; then
  echo '   "openports": [],'
else
  echo "${LISTENJSON},"
fi

# Output list of incoming connections (i.e. connections to ports we are listening to)
INCOMING=$(\
ss  -4  --numeric --oneline  --no-header  state CONNECTED '( '$INTERNAL_FILTER' ) and ( src = :'${LISTEN}' ) ' \
  | sed -E 's/:/ /g' \
  | tr  -s ' ' \
  | column --table \
            --table-columns netid,state,rq,sq,localaddress,localport,remoteaddress,remoteport \
            --table-hide netid,state,rq,sq,remoteport \
            --table-noheadings \
  | sort \
  | uniq -c \
  | column --json --table-columns count,localip,localport,remoteip --table-name incomingconnections --table-order localip,localport,remoteip,count \
  | sed '1d;$d' \
  )

if [ -z "$INCOMING" ]; then
  echo '   "incomingconnections": [],'
else
  echo "${INCOMING},"
fi


# Output list of outgoing connections (i.e. connections for ports we are not listening to)
OUTGOING=$( \
    ss  -4  --numeric --oneline  --no-header  state CONNECTED '( '$INTERNAL_FILTER' ) and not ( src = :'${LISTEN}' ) ' \
    | sed -E 's/:/ /g' \
    | tr  -s ' ' \
    | column --table \
              --table-columns netid,state,rq,sq,localaddress,localport,remoteaddress,remoteport \
              --table-hide netid,state,rq,sq,localport \
              --table-noheadings \
    | sort \
    | uniq -c \
    | column --json --table-columns count,localip,remoteip,remoteport --table-name outgoingconnections --table-order localip,remoteip,remoteport,count \
    | sed '1d;$d' \
  );

if [ -z "$OUTGOING" ]; then
  echo '   "outgoingconnections": [],'
else
  echo "${OUTGOING},"
fi

echo '   "timestamp": "'$(date +%s%N)'"'
echo "}"
