BASE=`dirname $0`/../
echo Working in ${BASE}/data
rm -f ${BASE}/data/Europe.geojson
mkdir -p ${BASE}/temp
for C in `cat ${BASE}/tools/velivole-config-countries.json | jq -r '. | keys[]'`; do
	if [ ! -r ${BASE}/temp/${C}-2.osm.json ]; then
		echo Downloading ${C} from OSM Overpass
		cat << EOF | curl -sd @- https://lz4.overpass-api.de/api/interpreter > ${BASE}/temp/${C}-2.osm.json
[out:json][timeout:400];
relation
	["ISO3166-1"="${C}"]
	["admin_level"="2"]
	["type"="boundary"]
	["boundary"="administrative"];
out geom;
EOF
		sleep 10
	fi
	osmtogeojson ${BASE}/temp/${C}-2.osm.json > ${BASE}/temp/${C}-2.geojson
	echo Merging ${C} to Europe.json
	ogr2ogr -nln Europe -where "OGR_GEOMETRY!='Point'" -append ${BASE}/data/Europe.geojson ${BASE}/temp/${C}-2.geojson
done
