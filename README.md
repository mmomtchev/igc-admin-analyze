# igc-admin-analyze

This is a tool for generating a breakdown of the overflown administrative boundaries from flight data in igc format

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install the dependencies.

```bash
pip install aerofiles argparse shapely rtree
```

## Usage

```bash
igc-admin-analyze.py -i <flightdata> -a <borders> [-q] [-v] [-s selected_areas]
```

If you want to verify that the included igc flight data corresponding to the current national record in France for paragliding distance over flatland is indeed a valid flatland flight, run
```bash
igc-admin-analyze.py -i record_de_france.igc -a FR -s "Yonne,Aube,Nièvre,1450201,Cher,51,Creuse"

Launch in Marne
Land in Corrèze
3.73% (272 of 7292) in Allier *
8.37% (610 of 7292) in Aube *
17.73% (1293 of 7292) in Cher *
2.56% (187 of 7292) in Corrèze
13.73% (1001 of 7292) in Creuse *
26.85% (1958 of 7292) in Marne *
6.82% (497 of 7292) in Nièvre *
20.21% (1474 of 7292) in Yonne *
97.44% (7105 of 7292) in selected areas
```
Areas can be specified by name, OSM Ref field (which happens to be the department number in France) or OSM ID

```bash
igc-admin-analyze.py -i record_de_france.igc -a Europe

Launch in France
Land in France
100.00% (7292 of 7292) in France
```



## Inner workings
This tool tries to be as precise as possible. For example the above record flight follows the Allier boundary for a few tens of kms. Simplified datasets produce incorrect results. The data used is the full scale OSM administrative boundary data which amounts to about 1,200,000 vertices for the French departments. As direct matching of 8000 to 10000 flight track points to such a number of vertices is not feasible, this tool uses a bounding box cache in a 2D R-tree that is saved across sessions.
First run over a new area tends to be somewhat slow, with subsequent runs being almos instantenous.

### Algorithm
For each point, check if there is a bounding box in the 2D R-tree and get the administrative area from it
Otherwise try to find the largest possible square bounding box corresponding to this point which does not cross into another administrative area and add it to the cache
At the end of the run, each administrative area is going to be represented by a set of square bounding boxes in a 2D R-tree

### OSM Overpass extraction
A script that can be used to re-extract the data from the Overpass server of OpenstreetMap is included, should you wish to extract the data yourself

## License
[MIT](https://choosealicense.com/licenses/mit/)