#!/usr/bin/env python3

""" Complete Scenario Generator from OSM.

    Author: Lara CODECA

    This program and the accompanying materials are made available under the
    terms of the Eclipse Public License 2.0 which is available at
    http://www.eclipse.org/legal/epl-2.0.
"""

import argparse
import cProfile
import io
import logging
import os
import pstats
import shutil
import subprocess
import sys

from xml.etree import ElementTree

import generateParkingAreasFromOSM
import generateTAZBuildingsFromOSM
import generateAmitranFromTAZWeights
import generateDefaultsActivityGen
import activitygen

if 'SUMO_HOME' in os.environ:
    sys.path.append(os.path.join(os.environ['SUMO_HOME'], 'tools'))
    import ptlines2flows
    import generateParkingAreaRerouters
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

def logs():
    """ Log init. """
    stdout_handler = logging.StreamHandler(sys.stdout)
    logging.basicConfig(handlers=[stdout_handler], level=logging.INFO,
                        format='[%(asctime)s] %(levelname)s: %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')

def get_options(cmd_args=None):
    """ Argument Parser. """
    parser = argparse.ArgumentParser(
        prog='complete.generator.py', usage='%(prog)s [options]',
        description='Complete scenario generator from OSM to the ActivityGen.')
    parser.add_argument(
        '--osm', type=str, dest='osm_file', required=True,
        help='OSM file.')
    parser.add_argument(
        '--out', type=str, dest='out_dir', required=True,
        help='Directory for all the output files.')
    parser.add_argument(
        '--profiling', dest='profiling', action='store_true',
        help='Enable Python3 cProfile feature.')
    parser.add_argument(
        '--no-profiling', dest='profiling', action='store_false',
        help='Disable Python3 cProfile feature.')
    parser.set_defaults(profiling=False)
    parser.add_argument(
        '--lefthand', dest='left_hand_traffic', action='store_true',
        help='Generate a left-hand traffic scenario.')
    parser.set_defaults(left_hand_traffic=False)
    return parser.parse_args(cmd_args)

## netconvert
DEFAULT_NETCONVERT = 'osm.netccfg'
DEFAULT_NET_XML = 'osm.net.xml'
DEFAULT_PT_STOPS_XML = 'osm_stops.add.xml'
DEFAULT_PT_LINES = 'osm_ptlines.xml'
DEFAULT_SIDE_PARKING_XML = 'osm_parking.xml'

## ptlines2flows
DEFAULT_PT_FLOWS = 'osm_pt.rou.xml'

## generateParkingAreasFromOSM
DEFAULT_PARKING_AREAS = 'osm_parking_areas.add.xml'

## merged parking files
DEFAULT_COMPLETE_PARKING_XML = 'osm_complete_parking_areas.add.xml'

## generateParkingAreaRerouters
DEFAULT_PARKING_REROUTERS_XML = 'osm_parking_rerouters.add.xml'

## polyconvert
DEFAULT_POLY_XML = 'osm_polygons.add.xml'

## generateTAZBuildingsFromOSM
DEFAULT_TAZ_OUTPUT_XML = 'osm_taz.xml'
DEFAULT_OD_OUTPUT_CSV = 'osm_taz_weight.csv'
DEFAULT_BUILDINGS_PREFIX = 'buildings/osm_buildings'

## generateAmitranFromTAZWeights
DEFAULT_ODMATRIX_AMITRAN_XML = 'osm_odmatrix_amitran.xml'

## generateDefaultsActivityGen
DEAFULT_GENERIC_AG_CONG = 'activitygen.json'
DEAFULT_SPECIFIC_AG_CONG = 'osm_activitygen.json'

## SUMO
DEFAULT_SUMOCFG = 'osm.sumocfg'

def _call_netconvert(filename, lefthand):
    """ Call netconvert using a subprocess. """
    netconvert_options = ['netconvert',
                          '-c', DEFAULT_NETCONVERT,
                          '--osm', filename,
                          '-o', DEFAULT_NET_XML,
                          '--ptstop-output', DEFAULT_PT_STOPS_XML,
                          '--ptline-output', DEFAULT_PT_LINES,
                          '--parking-output', DEFAULT_SIDE_PARKING_XML]
    if lefthand:
        netconvert_options.append('--lefthand')
    subprocess.call(netconvert_options)

def _call_pt_lines_to_flows():
    """ Call directly ptlines2flows from sumo/tools. """
    pt_flows_options = ptlines2flows.get_options(['-n', DEFAULT_NET_XML,
                                                  '-e', '86400',
                                                  '-p', '600',
                                                  '--random-begin',
                                                  '--seed', '42',
                                                  '--ptstops', DEFAULT_PT_STOPS_XML,
                                                  '--ptlines', DEFAULT_PT_LINES,
                                                  '-o', DEFAULT_PT_FLOWS,
                                                  '--ignore-errors',
                                                  '--vtype-prefix', 'pt_',
                                                  '--verbose'])
    ptlines2flows.main(pt_flows_options)

def _call_generate_parking_areas_from_osm(filename):
    """ Call directly generateParkingAreasFromOSM from SUMOActivityGen. """
    parking_options = ['--osm', filename, '--net', DEFAULT_NET_XML, '--out', DEFAULT_PARKING_AREAS]
    generateParkingAreasFromOSM.main(parking_options)

def _merge_parking_files(side_parking, parking_areas, complete_parking):
    """ Merge the two additional files containing parkings into one. """

    side_parking_struct = ElementTree.parse(side_parking).getroot()
    parking_areas_struct = ElementTree.parse(parking_areas).getroot()

    for element in parking_areas_struct:
        side_parking_struct.append(element)

    merged_parking = ElementTree.ElementTree(side_parking_struct)
    merged_parking.write(open(complete_parking, 'wb'))

def _call_generate_parking_area_rerouters():
    """ Call directly generateParkingAreaRerouters from sumo/tools. """
    rerouters_options = ['-a', DEFAULT_COMPLETE_PARKING_XML,
                         '-n', DEFAULT_NET_XML,
                         '--max-number-alternatives', '10',
                         '--max-distance-alternatives', '1000.0',
                         '--min-capacity-visibility-true', '50',
                         '--max-distance-visibility-true', '1000.0',
                         '-o', DEFAULT_PARKING_REROUTERS_XML]
    generateParkingAreaRerouters.main(rerouters_options)

def _call_polyconvert(filename):
    """ Call polyconvert using a subprocess. """
    polyconvert_options = ['polyconvert',
                           '--osm', filename,
                           '--net', DEFAULT_NET_XML,
                           '-o', DEFAULT_POLY_XML]
    subprocess.call(polyconvert_options)

def _call_generate_taz_buildings_from_osm(filename):
    """ Call directly generateTAZBuildingsFromOSM from SUMOActivityGen. """
    taz_buildings_options = ['--osm', filename,
                             '--net', DEFAULT_NET_XML,
                             '--taz-output', DEFAULT_TAZ_OUTPUT_XML,
                             '--od-output', DEFAULT_OD_OUTPUT_CSV,
                             '--poly-output', DEFAULT_BUILDINGS_PREFIX]
    generateTAZBuildingsFromOSM.main(taz_buildings_options)

def _call_generate_amitran_from_taz_weights():
    """ Call directly generateAmitranFromTAZWeights from SUMOActivityGen. """
    odmatrix_options = ['--taz-weights', DEFAULT_OD_OUTPUT_CSV,
                        '--out', DEFAULT_ODMATRIX_AMITRAN_XML,
                        '--density', '3000.0']
    generateAmitranFromTAZWeights.main(odmatrix_options)

def _call_generate_defaults_activitygen():
    """ Call directly generateDefaultsActivityGen from SUMOActivityGen. """
    default_options = ['--conf', DEAFULT_GENERIC_AG_CONG,
                       '--od-amitran', DEFAULT_ODMATRIX_AMITRAN_XML,
                       '--out', DEAFULT_SPECIFIC_AG_CONG]
    generateDefaultsActivityGen.main(default_options)

def _call_activitygen():
    """ Call directly activitygen from SUMOActivityGen. """
    activitygen_options = ['-c', DEAFULT_SPECIFIC_AG_CONG]
    activitygen.main(activitygen_options)

def _add_rou_to_default_sumocfg():
    """ Load the configuration file used by activitygen and add the newly generated routes. """
    route_files = ''
    for item in os.listdir():
        if '.rou.xml' in item:
            route_files += item + ','
    route_files = route_files.strip(',')

    xml_tree = ElementTree.parse(DEFAULT_SUMOCFG).getroot()
    for field in xml_tree.iter('route-files'):
        ## it should be only one, tho.
        field.attrib['value'] = route_files
    new_sumocfg = ElementTree.ElementTree(xml_tree)
    new_sumocfg.write(open(DEFAULT_SUMOCFG, 'wb'))

def _call_sumo():
    """ Call SUMO using a subprocess. """
    subprocess.call(['sumo', '-c', DEFAULT_SUMOCFG])

def main(cmd_args):
    """ Complete Scenario Generator. """

    args = get_options(cmd_args)

    ## ========================              PROFILER              ======================== ##
    if args.profiling:
        profiler = cProfile.Profile()
        profiler.enable()
    ## ========================              PROFILER              ======================== ##

    os.makedirs(args.out_dir, exist_ok=True)
    shutil.copy(args.osm_file, args.out_dir)
    args.osm_file = os.path.basename(args.osm_file)
    shutil.copy('defaults/activitygen.json', args.out_dir)
    shutil.copy('defaults/basic.vType.xml', args.out_dir)
    shutil.copy('defaults/duarouter.sumocfg', args.out_dir)
    shutil.copy('defaults/osm.netccfg', args.out_dir)
    shutil.copy('defaults/osm.sumocfg', args.out_dir)
    os.chdir(args.out_dir)

    logging.info('Generate the net.xml with all the additional components '
                 '(public transports, parkings, ..)')
    _call_netconvert(args.osm_file, args.left_hand_traffic)

    logging.info('Generate flows for public transportation using ptlines2flows.')
    _call_pt_lines_to_flows()

    logging.info('Generate parking area location and possibly merge it with the one provided '
                 'by netconvert.')
    _call_generate_parking_areas_from_osm(args.osm_file)
    _merge_parking_files(DEFAULT_SIDE_PARKING_XML, DEFAULT_PARKING_AREAS,
                         DEFAULT_COMPLETE_PARKING_XML)

    logging.info('Generate parking area rerouters using tools/generateParkingAreaRerouters.py')
    _call_generate_parking_area_rerouters()

    logging.info('Generate polygons using polyconvert.')
    _call_polyconvert(args.osm_file)

    logging.info('Generate TAZ from administrative boundaries, TAZ weights using buildings and '
                 ' PoIs and the buildings infrastructure.')
    os.makedirs('buildings', exist_ok=True)
    _call_generate_taz_buildings_from_osm(args.osm_file)

    logging.info('Generate the default values for the activity based mobility generator. ')
    _call_generate_amitran_from_taz_weights()
    _call_generate_defaults_activitygen()

    logging.info('Mobility generation using SUMOActivityGen.')
    _call_activitygen()

    logging.info('Generate the SUMO configuration file and launch sumo-gui.')
    _add_rou_to_default_sumocfg()
    _call_sumo()

    ## ========================              PROFILER              ======================== ##
    if args.profiling:
        profiler.disable()
        results = io.StringIO()
        pstats.Stats(profiler, stream=results).sort_stats('cumulative').print_stats(25)
        print(results.getvalue())
    ## ========================              PROFILER              ======================== ##

    logging.info('Done.')

if __name__ == '__main__':
    logs()
    main(sys.argv[1:])
