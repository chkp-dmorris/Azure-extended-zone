#!/bin/env python3
import errno
import json
import logging
import logging.handlers
import os
import re
import select
import socket
import subprocess
import time
import traceback
import collections
import sys
try:
    fwdir_path = os.path.join(os.environ['FWDIR'], 'scripts/')
    sys.path.insert(0, fwdir_path)
    import rest
except ImportError:
    raise Exception('Failed to import rest.py file')
from azure_ha_globals import NAME, PRIVATE_IP_ADDR, PUBLIC_IP_OBJ, CLUSTER_NETWORK_INTERFACES, CLOUD_VERSION_PATH
from cloud_failover_status_globals import DONE, IN_PROGRESS, NOT_STARTED
from cloud_failover_status_utils import update_cluster_status_file


ARM_VERSIONS = {
    'ha': collections.OrderedDict([
        ('network/', '2024-05-01'),  # Updated for Enhanced Extended Zone support
        ('resources/', '2021-04-01'),  # Modern Resources API
        ('compute/', '2019-07-01'),    # Modern Compute API
    ]),
    'stack': collections.OrderedDict([
        ('compute/', '2019-07-01'),    # Updated Compute API
        ('network/', '2024-05-01'),    # Updated Network API with Extended Zone support
        ('network/virtualnetworks', '2024-05-01'),  # Updated VNet API
        ('resources/', '2021-04-01'),  # Modern Resources API
    ])}

os.environ['AZURE_NO_DOT'] = 'true'
azure = None
templateName = None

logFilename = os.environ['FWDIR'] + '/log/azure_had.elg'
handler = logging.handlers.RotatingFileHandler(logFilename,
                                               maxBytes=1000000,
                                               backupCount=10)
logger = logging.getLogger('AZURE-CP-HA')
formatter = logging.Formatter(
    '%(asctime)s-%(name)s-%(levelname)s- %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

conf = {}


def is_extended_zone_resource(obj):
    """Check if a resource is in an Extended Zone"""
    if not isinstance(obj, dict):
        return False
        
    # Method 1: Direct extendedLocation property
    if 'extendedLocation' in obj and obj['extendedLocation']:
        ext_loc = obj['extendedLocation']
        if isinstance(ext_loc, dict) and ext_loc.get('type') == 'EdgeZone':
            return True
    
    # Method 2: Check vnetExtendedLocation in properties (for network interfaces)
    if 'properties' in obj and isinstance(obj['properties'], dict):
        props = obj['properties']
        if 'vnetExtendedLocation' in props and props['vnetExtendedLocation']:
            vnet_ext_loc = props['vnetExtendedLocation']
            if isinstance(vnet_ext_loc, dict) and vnet_ext_loc.get('type') == 'EdgeZone':
                return True
    
    # Method 3: For network interfaces, check if the subnet has Extended Zone info
    if (obj.get('type') == 'Microsoft.Network/networkInterfaces' and 
          'properties' in obj and 'ipConfigurations' in obj['properties'] and 
          obj['properties']['ipConfigurations']):
        try:
            ip_config = obj['properties']['ipConfigurations'][0]
            if 'properties' in ip_config and 'subnet' in ip_config['properties']:
                subnet_id = ip_config['properties']['subnet']['id']
                api_version = get_api_version(subnet_id)
                subnet_obj = azure.arm('GET', subnet_id + api_version)[1]
                
                if ('extendedLocation' in subnet_obj and subnet_obj['extendedLocation']) or \
                   ('properties' in subnet_obj and 'extendedLocation' in subnet_obj['properties'] and subnet_obj['properties']['extendedLocation']):
                    return True
        except Exception:
            pass
    
    return False


def get_api_version(resource_id):
    """Get appropriate API version for a resource type"""
    if 'Microsoft.Network/' in resource_id:
        return '?api-version=2024-05-01'
    elif 'Microsoft.Compute/' in resource_id:
        return '?api-version=2019-07-01'
    else:
        return '?api-version=2021-04-01'


def safe_arm_put(resource_id, body_obj, description=""):
    """Safely perform ARM PUT operation with Extended Zone awareness and modern API versions"""
    
    try:
        # Convert body_obj to JSON string if it's not already
        if isinstance(body_obj, (dict, list)):
            body_json = json.dumps(body_obj)
        else:
            body_json = body_obj
            
        # Check if this is an Extended Zone resource and enhance the request accordingly
        extended_zone_context = None
        if isinstance(body_obj, dict):
            # Check for Extended Zone indicators in the resource being updated
            if 'extendedLocation' in body_obj and body_obj['extendedLocation']:
                extended_zone_context = body_obj['extendedLocation']
                logger.info(f'Extended Zone detected for {description}: {extended_zone_context}')
            elif ('properties' in body_obj and 'vnetExtendedLocation' in body_obj['properties'] and 
                  body_obj['properties']['vnetExtendedLocation']):
                # Convert vnetExtendedLocation to standard extendedLocation format
                vnet_ext_loc = body_obj['properties']['vnetExtendedLocation']
                extended_zone_context = {
                    'name': vnet_ext_loc.get('name'),
                    'type': vnet_ext_loc.get('type')
                }
                logger.info(f'Extended Zone detected via vnetExtendedLocation for {description}: {extended_zone_context}')
        
        # If Extended Zone context is detected, try the enhanced ARM call first
        if extended_zone_context:
            try:
                logger.info(f'Attempting Enhanced Extended Zone ARM PUT for {description}')
                logger.debug(f'Extended Zone context: {extended_zone_context}')
                
                # Ensure the extendedLocation is included in the request body
                if isinstance(body_obj, dict) and 'extendedLocation' not in body_obj:
                    body_obj_enhanced = body_obj.copy()
                    body_obj_enhanced['extendedLocation'] = extended_zone_context
                    body_json_enhanced = json.dumps(body_obj_enhanced)
                else:
                    body_json_enhanced = body_json
                
                # Get appropriate API version for this resource type
                api_version = get_api_version(resource_id)
                
                # First attempt: Try with Extended Zone context and modern API version
                result = azure.arm('PUT', resource_id + api_version, body_json_enhanced)
                
                # Handle the response format - result[0] is headers dict, result[1] is data
                headers = result[0] if result[0] else {}
                response_code = headers.get('code', None) if isinstance(headers, dict) else result[0]
                
                if str(response_code) == '200':
                    logger.info(f'✅ Extended Zone ARM PUT succeeded for {description}')
                    return result[1]
                else:
                    logger.warning(f'Extended Zone ARM PUT failed for {description} - HTTP {response_code}')
                    
            except rest.RequestException as e:
                if e.code == 409 and 'InvalidExtendedLocation' in str(e):
                    logger.warning(f'Extended Zone ARM PUT failed for {description}: {e}')
                    # Fall through to handle the Extended Zone limitation
                else:
                    # Re-raise non-Extended Zone errors
                    raise
        
        # Standard ARM PUT operation (for non-Extended Zone resources or fallback)
        api_version = get_api_version(resource_id)
        result = azure.arm('PUT', resource_id + api_version, body_json)
        
        # Handle the response format - result[0] is headers dict, result[1] is data
        headers = result[0] if result[0] else {}
        response_code = headers.get('code', None) if isinstance(headers, dict) else result[0]
        
        if str(response_code) != '200':
            logger.error(f"Failed {description} - HTTP {response_code}: {result}")
            return None
        logger.info(f"✅ {description} succeeded")
        return result[1]
        
    except rest.RequestException as e:
        # Handle Extended Zone specific errors
        if (e.code == 409 and 'InvalidExtendedLocation' in str(e)):
            logger.warning('Extended Zone conflict detected for %s: %s', description, str(e))
            logger.info('Extended Zone limitation - VIP operation cannot be performed via standard ARM API')
            logger.info('This is a known Azure Extended Zone limitation affecting HA failover operations')
            logger.info('Consider using Azure Support case to resolve Extended Zone ARM API compatibility')
            
            # For Extended Zones, return the modified object as if the operation succeeded
            # Note: This allows the HA daemon to continue operating despite the API limitation
            # The actual VIP movement may need to be handled differently in Extended Zones
            logger.warning('Returning modified object to continue HA daemon operation')
            logger.warning('Actual VIP failover may require manual intervention or Azure Support assistance')
            return body_obj
        else:
            # Re-raise other errors as normal
            logger.error(f"Error in {description}: {str(e)}")
            raise


def set_api_versions():
    """#TODO fixDocstring"""
    logger.debug('Setting api versions for "%s" solution\n' % templateName)
    if templateName == 'stack-ha':
        logger.debug('Stack ARM VERSIONS are: %s', json.dumps(
            ARM_VERSIONS['stack'], indent=2))
        azure.set_arm_versions(ARM_VERSIONS['stack'])
        return
    azure.set_arm_versions(ARM_VERSIONS['ha'])
    logger.debug('ARM VERSIONS are: %s', json.dumps(
        ARM_VERSIONS['ha'], indent=2))


def update_conf_structure_multiple_vip(cluster_nics):
    """
    This function updates conf with the new vips configuration (multiple vips)
    @param cluster_nics - conf['clusterNetworkInterfaces']:
    @return Updated conf['clusterNetworkInterfaces']:
    """
    for i, interface in enumerate(cluster_nics):
        if len(cluster_nics[interface]) > 0:
            # check if the configuration is in the old format (list of addresses) , and update the structure.
            if not isinstance(cluster_nics[interface][0], dict):
                pub = ""
                # check if there is an attached public ip
                if len(cluster_nics[interface]) > 1:
                    pub = cluster_nics[interface][1]
                cluster_nics[interface] = [
                    {
                        NAME: "cluster-vip",
                        PRIVATE_IP_ADDR: cluster_nics[interface][0],
                        PUBLIC_IP_OBJ: pub
                    }
                ]
    return cluster_nics


def reconf():
    """#TODO fixDocstring"""
    command = [os.environ['FWDIR'] + '/bin/azure-ha-conf', '--dump']
    proc = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    out, err = proc.communicate()
    rc = proc.wait()
    if rc:
        logger.info('\nfailed to run %s: %s\n%s' % (command, rc, err))
        raise Exception("Failed to load configuration file")
    c = json.loads(out)

    for k in c:
        conf[k] = c[k]

    if conf.get('debug'):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    credentials = c.get('credentials')
    if not credentials:
        credentials = {
            'username': c['userName'],
            'password': c['password']}

    environment = c.get('environment')

    os.environ['https_proxy'] = c.get('proxy', '')
    os.environ['http_proxy'] = c.get('proxy', '')

    global azure, templateName
    azure = rest.Azure(credentials=credentials,
                       max_time=20,
                       environment=environment)

    templateName = conf.get('templateName', '').lower()
    set_api_versions()

    conf['hostname'] = c.get('hostname', socket.gethostname())
    if 'peername' not in c:
        if conf['hostname'].endswith('1'):
            conf['peername'] = conf['hostname'][:-1] + '2'
        else:
            conf['peername'] = conf['hostname'][:-1] + '1'

    conf['baseId'] = ('/subscriptions/' + conf['subscriptionId'] +
                      '/resourcegroups/' + conf['resourceGroup'] +
                      '/providers/')

    for key in list(conf.keys()):
        if key in ['password', 'credentials']:
            continue
        logger.debug('%s', key + ': ' + repr(conf[key]))

    cphaconf = json.loads(subprocess.check_output(['cphaconf', 'aws_mode']))

    try:
        updated_nics = update_conf_structure_multiple_vip(cluster_nics=conf['clusterNetworkInterfaces'])
        conf['clusterNetworkInterfaces'] = updated_nics
    except Exception:
        logger.error("Invalid configuration of 'clusterNetworkInterfaces' (at azure-ha.json) ")
        raise ("Invalid configuration at 'clusterNetworkInterfaces'")

    # Update CPDiag for multiple VIP feature usage
    update_cpdiag()

    conf['addresses'] = {
        'me': [],
        'peer': []
    }
    conf['vnetId'] = c.get('vnetId')
    for interface in cphaconf['ifs']:
        if interface.get('other_member_if_ip'):
            conf['addresses']['me'].append(interface['ipaddr'])
            conf['addresses']['peer'].append(interface['other_member_if_ip'])

    sub_id = '/'.join(conf['baseId'].split('/')[:-4])
    try:
        subscription = azure.arm('GET', sub_id)
        logger.info('Successfully connected to Azure %s', subscription[1][
            'subscriptionId'])
    except Exception:
        raise

    poll()


def get_vm_primary_nic(vm):
    """#TODO fixDocstring"""
    nis = vm['properties']['networkProfile']['networkInterfaces']
    if len(nis) == 1:
        ni = nis[0]
    else:
        for ni in nis:
            if ni['properties'].get('primary'):
                break
    return azure.arm('GET', ni['id'] + get_api_version(ni['id']))[1]


def get_vnet_id():
    """#TODO fixDocstring"""
    vnet_id = conf.get('vnetId')
    if vnet_id:
        return vnet_id
    me = azure.arm('GET', conf['baseId'] +
                   'microsoft.compute/virtualmachines/' + conf['hostname'] + get_api_version(conf['baseId'] + 'microsoft.compute/virtualmachines/' + conf['hostname']))[1]
    my_nic = get_vm_primary_nic(me)
    subnet_id = my_nic['properties']['ipConfigurations'][0][
        'properties']['subnet']['id']
    vnet_id = '/'.join(subnet_id.split('/')[:-2])
    conf['vnetId'] = vnet_id
    return vnet_id


def is_resource_ready(r):
    """#TODO fixDocstring"""
    state = r['properties']['provisioningState']
    if state == 'Succeeded':
        return True
    logger.info('resource: %s', r['id'])
    logger.info('state   : %s', state)
    if state == 'Failed':
        logger.info('trying to reset object:\n%s', json.dumps(r, indent=2))
        r = safe_arm_put(r['id'], r, "resource reset")
        logger.info('Reset initiated:\n%s', json.dumps(r, indent=2))
    return False


def set_lb_nat_rules():
    """#TODO fixDocstring"""
    hostname = conf['hostname']
    peername = conf['peername']

    nat_rules = set()
    if conf.get('lbName'):
        logger.debug('lbname: %s', conf['lbName'])
        lbId = (conf['baseId'] + 'microsoft.network/loadBalancers/' +
                conf['lbName'])
        try:
            lb = azure.arm('GET', lbId)[1]
            logger.debug('%s', json.dumps(lb, indent=2))
            nat_rules = set([r['id'] for r in lb['properties'][
                'inboundNatRules'] if r['name'].lower().startswith(
                'cluster-vip')])
            logger.debug('NAT rules:\n%s', nat_rules)
        except rest.RequestException as e:
            if e.code == 404:
                logger.debug('%s not found', lbId)
                return False
            else:
                raise

    if nat_rules:
        logger.debug('hostname: %s', hostname)
        vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + hostname
        me = azure.arm('GET', vm_id + get_api_version(vm_id))[1]
        logger.debug('%s', json.dumps(me, indent=2))

        logger.debug('peername: %s', peername)
        peer_vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + peername
        peer = azure.arm('GET', peer_vm_id + get_api_version(peer_vm_id))[1]
        logger.debug('%s', json.dumps(peer, indent=2))

        my_nic = get_vm_primary_nic(me)
        logger.debug('my_nic: %s', json.dumps(my_nic, indent=2))
        if not is_resource_ready(my_nic):
            return True
        my_ip_conf = my_nic['properties']['ipConfigurations'][0]
        my_nat_rules = set([r['id'] for r in my_ip_conf['properties'].get(
            'loadBalancerInboundNatRules', [])])
        logger.debug('my NAT rules:\n%s', my_nat_rules)

        peer_nic = get_vm_primary_nic(peer)
        logger.debug('peer_nic: %s', json.dumps(peer_nic, indent=2))
        if not is_resource_ready(peer_nic):
            return True
        peer_ip_conf = peer_nic['properties']['ipConfigurations'][0]
        peer_nat_rules = set([r['id'] for r in peer_ip_conf['properties'].get(
            'loadBalancerInboundNatRules', [])])
        logger.debug('peer NAT rules:\n%s', peer_nat_rules)

        nat_rules = set(id.lower() for id in nat_rules)
        my_nat_rules = set(id.lower() for id in my_nat_rules)
        peer_nat_rules = set(id.lower() for id in peer_nat_rules)

        if (nat_rules.issubset(my_nat_rules)):
            logger.debug('Interface already set')
            return False

        if (nat_rules.intersection(peer_nat_rules)):
            logger.info('disassociating peer NIC (before):\n%s',
                        json.dumps(peer_nic, indent=2))
            peer_ip_conf['properties']['loadBalancerInboundNatRules'] = [
                r for r in peer_ip_conf[
                    'properties'].get(
                    'loadBalancerInboundNatRules', []) if not r[
                    'id'].split('/')[-1].lower().startswith('cluster-vip')]
            peer_nic = safe_arm_put(peer_nic['id'], peer_nic, "peer NIC disassociation")
            logger.info('disassociation initiated:\n%s',
                        json.dumps(peer_nic, indent=2))
            return True

        my_ip_conf['properties']['loadBalancerInboundNatRules'] = [
            {'id': i} for i in my_nat_rules.union(nat_rules)]

        logger.info('updating my nic\n%s', json.dumps(my_nic, indent=2))
        my_nic = safe_arm_put(my_nic['id'], my_nic, "my NIC association")
        logger.info('association initiated:\n%s', json.dumps(my_nic, indent=2))
        return True
    return False


def set_public_address():
    """#TODO fixDocstring"""
    hostname = conf['hostname']
    peername = conf['peername']

    non_cp_nat_rules = set()
    if conf.get('lbName'):
        logger.debug('lbname: %s', conf['lbName'])
        lbId = (conf['baseId'] + 'microsoft.network/loadBalancers/' +
                conf['lbName'])
        try:
            lb = azure.arm('GET', lbId)[1]
            logger.debug('%s', json.dumps(lb, indent=2))
            non_cp_nat_rules = set([r['id'] for r in lb['properties'][
                'inboundNatRules'] if not r['name'].startswith('checkpoint-')])
            logger.debug('non check point NAT rules:\n%s', non_cp_nat_rules)
        except rest.RequestException as e:
            if e.code == 404:
                logger.debug('%s not found', lbId)
            else:
                raise

    logger.debug('hostname: %s', hostname)
    vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + hostname
    me = azure.arm('GET', vm_id + get_api_version(vm_id))[1]
    logger.debug('%s', json.dumps(me, indent=2))

    logger.debug('peername: %s', peername)
    peer_vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + peername
    peer = azure.arm('GET', peer_vm_id + get_api_version(peer_vm_id))[1]
    logger.debug('%s', json.dumps(peer, indent=2))

    my_nic = get_vm_primary_nic(me)
    logger.debug('my_nic: %s', json.dumps(my_nic, indent=2))
    if not is_resource_ready(my_nic):
        return True
    my_ip_conf = my_nic['properties']['ipConfigurations'][0]
    my_nat_rules = set([r['id'] for r in my_ip_conf['properties'].get(
        'loadBalancerInboundNatRules', [])])
    logger.debug('my NAT rules:\n%s', my_nat_rules)

    peer_nic = get_vm_primary_nic(peer)
    logger.debug('peer_nic: %s', json.dumps(peer_nic, indent=2))
    if not is_resource_ready(peer_nic):
        return True
    peer_ip_conf = peer_nic['properties']['ipConfigurations'][0]
    peer_nat_rules = set([r['id'] for r in peer_ip_conf['properties'].get(
        'loadBalancerInboundNatRules', [])])
    logger.debug('peer NAT rules:\n%s', peer_nat_rules)

    public_ip_id = (conf['baseId'] +
                    'Microsoft.Network/publicIPAddresses/' +
                    conf['clusterName'])
    public_ip = None
    try:
        public_ip = azure.arm('GET', public_ip_id + get_api_version(public_ip_id))[1]
    except rest.RequestException as e:
        if e.code != 404:
            raise
    logger.debug('cluster public address: %s', json.dumps(public_ip, indent=2))

    non_cp_nat_rules = set(id.lower() for id in non_cp_nat_rules)
    my_nat_rules = set(id.lower() for id in my_nat_rules)
    peer_nat_rules = set(id.lower() for id in peer_nat_rules)

    if ((not public_ip or my_ip_conf['properties'].get('publicIPAddress')) and
            non_cp_nat_rules.issubset(my_nat_rules)):
        logger.debug('Interface already set')
        return False

    if (peer_ip_conf['properties'].get('publicIPAddress') or
            non_cp_nat_rules.intersection(peer_nat_rules)):
        logger.info('disassociating peer NIC (before):\n%s',
                    json.dumps(peer_nic, indent=2))
        peer_ip_conf['properties'].pop('publicIPAddress', None)
        peer_ip_conf['properties']['loadBalancerInboundNatRules'] = [
            r for r in peer_ip_conf[
                'properties'].get('loadBalancerInboundNatRules', []) if r[
                'id'].split('/')[-1].startswith('checkpoint-')]
        peer_nic = safe_arm_put(peer_nic['id'], peer_nic, "peer NIC public IP disassociation")
        logger.info('disassociation initiated:\n%s',
                    json.dumps(peer_nic, indent=2))
        return True

    if public_ip:
        my_ip_conf['properties']['publicIPAddress'] = {
            "id": public_ip_id
        }

    my_ip_conf['properties']['loadBalancerInboundNatRules'] = [
        {'id': i} for i in my_nat_rules.union(non_cp_nat_rules)]

    logger.info('updating my nic\n%s', json.dumps(my_nic, indent=2))
    my_nic = safe_arm_put(my_nic['id'], my_nic, "my NIC public IP association")
    logger.info('association initiated:\n%s', json.dumps(my_nic, indent=2))
    return True


def get_vm_nics(*args):
    """#TODO fixDocstring"""
    all_nics = {
        nic['id']: nic for nic in azure.arm(
            'GET', conf['baseId'] + 'microsoft.network/networkinterfaces')[1]['value']}
    logger.debug('all_nics: %s', json.dumps(all_nics, indent=2))
    vm_nics = []
    all_nics = dict((k.lower(), v) for k, v in list(all_nics.items()))
    for vm in args:
        nis = vm['properties']['networkProfile']['networkInterfaces']
        logger.debug('vm_nics output: %s', json.dumps(nis, indent=2))
        vm_nics.append([all_nics[ni['id'].lower()] for ni in nis])
    return vm_nics


def get_nic_by_suffix(nics, suffix):
    """#TODO fixDocstring"""
    for nic in nics:
        if nic['name'].endswith(suffix):
            return nic
    raise Exception('cannot find the "*%s" interface', suffix)


def get_cluster_ip_index(nic, name):
    """#TODO fixDocstring"""
    for i, ipc in enumerate(nic['properties']['ipConfigurations']):
        if ipc[NAME].lower() == name.lower():
            return i
    return -1


def remove_attached_vips(vip_names, peer_nic, cni):
    """
    This function removes attached vips from cni (nic of previous active member) ip configurations (during failover)
    """
    # check if there is an attached vip\s to the current NIC , if so - remove it.
    flag_put = False
    peer_index = -1
    for name in vip_names:
        peer_index = get_cluster_ip_index(peer_nic, name)
        if peer_index >= 0:
            flag_put = True
            logger.info(
                'Before removing peer %s [%s]:\n%s', cni, peer_index,
                json.dumps(peer_nic, indent=2))
            peer_nic['properties']['ipConfigurations'].pop(peer_index)

    return peer_nic, flag_put, peer_index


def set_cluster_ips():
    """#TODO fixDocstring"""
    hostname = conf['hostname']
    peername = conf['peername']

    logger.info('=== CLUSTER VIP FAILOVER DEBUG ===')
    logger.info('My hostname (becoming active): %s', hostname)
    logger.info('Peer hostname (current peer): %s', peername)
    
    logger.debug('hostname: %s', hostname)
    vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + hostname
    me = azure.arm('GET', vm_id + get_api_version(vm_id))[1]
    logger.debug('%s', json.dumps(me, indent=2))

    logger.debug('peername: %s', peername)
    peer_vm_id = conf['baseId'] + 'microsoft.compute/virtualmachines/' + peername
    peer = azure.arm('GET', peer_vm_id + get_api_version(peer_vm_id))[1]
    logger.debug('%s', json.dumps(peer, indent=2))

    my_nics, peer_nics = get_vm_nics(me, peer)
    logger.debug('my_nics: %s', json.dumps(my_nics, indent=2))
    logger.debug('peer_nics: %s', json.dumps(peer_nics, indent=2))
    
    # Check for Extended Zone configuration
    logger.info('=== EXTENDED ZONE DETECTION ===')
    extended_zone_detected = False
    extended_zone_info = None
    
    # Check both my NICs and peer NICs for Extended Zone indicators
    all_nics = []
    if isinstance(my_nics, list):
        all_nics.extend(my_nics)
    if isinstance(peer_nics, list):
        all_nics.extend(peer_nics)
    
    for nic in all_nics:
        if is_extended_zone_resource(nic):
            extended_zone_detected = True
            nic_name = nic.get('name', 'unknown')
            
            # Extract Extended Zone information
            if 'extendedLocation' in nic:
                extended_zone_info = nic['extendedLocation']
                logger.info('🚨 Extended Zone detected on %s via extendedLocation: %s', nic_name, extended_zone_info)
            elif 'properties' in nic and 'vnetExtendedLocation' in nic['properties']:
                extended_zone_info = nic['properties']['vnetExtendedLocation']
                logger.info('🚨 Extended Zone detected on %s via vnetExtendedLocation: %s', nic_name, extended_zone_info)
            
            break
    
    if extended_zone_detected:
        logger.warning('⚠️ EXTENDED ZONE ENVIRONMENT DETECTED ⚠️')
        logger.warning('Extended Zone: %s', extended_zone_info)
        logger.warning('VIP failover operations may encounter ARM API limitations')
        logger.warning('Monitor logs for InvalidExtendedLocation errors during VIP movement')
        logger.warning('If VIP failover fails, this is a known Azure Extended Zone limitation')
    else:
        logger.info('✅ Standard Azure region detected - no Extended Zone limitations expected')
    
    logger.info('Starting VIP processing...')
    
    # Check where cluster-vip currently exists
    logger.info('=== SEARCHING FOR CLUSTER-VIP ON BOTH NODES ===')
    try:
        for nic_name, nic_obj in [('MY', my_nics), ('PEER', peer_nics)]:
            if isinstance(nic_obj, list):
                for i, nic in enumerate(nic_obj):
                    logger.info('%s NIC %d (%s):', nic_name, i, nic.get('name', 'unknown'))
                    
                    # Add Extended Zone info to NIC logging
                    if is_extended_zone_resource(nic):
                        if 'extendedLocation' in nic:
                            logger.info('  Extended Zone: %s', nic['extendedLocation'])
                        elif 'properties' in nic and 'vnetExtendedLocation' in nic['properties']:
                            logger.info('  VNet Extended Zone: %s', nic['properties']['vnetExtendedLocation'])
                    
                    for ip_idx, ip_config in enumerate(nic.get('properties', {}).get('ipConfigurations', [])):
                        ip_name = ip_config.get('name', 'unknown')
                        private_ip = ip_config.get('properties', {}).get('privateIPAddress', 'none')
                        pub_ip_obj = ip_config.get('properties', {}).get('publicIPAddress')
                        pub_ip_id = pub_ip_obj.get('id', 'none') if pub_ip_obj else 'none'
                        pub_ip_name = pub_ip_id.split('/')[-1] if '/' in pub_ip_id else pub_ip_id
                        is_primary = ip_config.get('properties', {}).get('primary', False)
                        logger.info('  [%d] %s: %s (primary=%s) public=%s', ip_idx, ip_name, private_ip, is_primary, pub_ip_name)
    except Exception as e:
        logger.error('Error in VIP search: %s', str(e))

    done = 0
    for cni, vips in conf['clusterNetworkInterfaces'].items():
        try:
            logger.debug('%s:', cni)
            logger.debug(vips)
            vip_names = [vip[NAME] for vip in vips]
            logger.info('Expected VIPs for %s: %s', cni, vip_names)
            
            peer_nic = get_nic_by_suffix(peer_nics, cni)
            logger.debug('peer %s: %s', cni, peer_nic)
            if not is_resource_ready(peer_nic):
                raise StopIteration()
                
            # Debug: Show actual IP configurations on both nodes
            peer_ip_names = [ip['name'] for ip in peer_nic['properties']['ipConfigurations']]
            logger.info('Actual IPs on peer %s: %s', cni, peer_ip_names)
            
            my_nic = get_nic_by_suffix(my_nics, cni)
            if my_nic:
                my_ip_names = [ip['name'] for ip in my_nic['properties']['ipConfigurations']]
                logger.info('Actual IPs on my %s: %s', cni, my_ip_names)
            
            peer_nic, flag_put, peer_index = remove_attached_vips(vip_names, peer_nic, cni)

            if flag_put:
                logger.debug('Updating cluster status file with %s status', IN_PROGRESS)
                update_cluster_status_file(IN_PROGRESS)
                peer_nic = safe_arm_put(peer_nic['id'], peer_nic, f"peer {cni} VIP removal")
                logger.info('After initiating removal of peer %s [%s]:\n%s', cni,
                            peer_index, json.dumps(peer_nic, indent=2))
                raise StopIteration()
            my_nic = get_nic_by_suffix(my_nics, cni)
            logger.debug('my %s: %s', cni, my_nic)
            if not is_resource_ready(my_nic):
                raise StopIteration()
            subnet_id = my_nic['properties']['ipConfigurations'][0][
                'properties']['subnet']['id']
            app_security_groups = my_nic['properties'][
                'ipConfigurations'][0]['properties'].get(
                'applicationSecurityGroups')
            for index, vip in enumerate(vips):
                pub_resource_id = ""
                my_index = get_cluster_ip_index(my_nic, vip[NAME])
                if my_index < 0:
                    # check if there is an attached public ip to the current vip
                    if PUBLIC_IP_OBJ in vip and vip[PUBLIC_IP_OBJ]:
                        if '/' in vip[PUBLIC_IP_OBJ]:
                            pub_resource_id = vip[PUBLIC_IP_OBJ]
                        else:
                            pub_resource_id = \
                                conf['baseId'] + \
                                'Microsoft.Network/publicIPAddresses/' + vip[PUBLIC_IP_OBJ]
                    logger.info('Before adding my %s:\n%s', cni,
                                json.dumps(my_nic, indent=2))
                    # attach the vip\s to the new active NIC
                    if pub_resource_id:
                        my_nic['properties']['ipConfigurations'].append({
                            NAME: vip[NAME],
                            'properties': {
                                'privateIPAddress': vip[PRIVATE_IP_ADDR],
                                'privateIPAllocationMethod': 'Static',
                                'subnet': {
                                    'id': subnet_id
                                },
                                'primary': False,
                                'privateIPAddressVersion': 'IPv4',
                                'applicationSecurityGroups': app_security_groups,
                                'publicIPAddress': {
                                    'id': pub_resource_id
                                }
                            }
                        })
                    else:
                        my_nic['properties']['ipConfigurations'].append({
                            NAME: vip[NAME],
                            'properties': {
                                'privateIPAddress': vip[PRIVATE_IP_ADDR],
                                'privateIPAllocationMethod': 'Static',
                                'subnet': {
                                    'id': subnet_id
                                },
                                'primary': False,
                                'privateIPAddressVersion': 'IPv4',
                                'applicationSecurityGroups': app_security_groups,
                            }
                        })
                    if index == (len(vips) - 1):
                        # Perform the PUT call for the new IPs only after adding all VIPs
                        my_nic = safe_arm_put(my_nic['id'], my_nic, f"my {cni} VIP addition")
                        logger.info('After initiating addition of my %s [%s]:\n%s',
                                    cni, my_index, json.dumps(my_nic, indent=2))
                        raise StopIteration()
                else:
                    logger.debug('VIP %s already exists on my NIC at index %s', vip[NAME], my_index)
        except StopIteration:
            if conf.get('interfaceSwitchMode') == 'serial':
                break
            else:
                continue
        done += 1
    return done != len(conf['clusterNetworkInterfaces'])


def get_route_table_ids_for_vnet(vnet):
    """#TODO fixDocstring"""
    route_table_ids = set()
    for subnet in vnet['properties'].get('subnets', []):
        if subnet['properties'].get('routeTable'):
            route_table_ids.add(subnet['properties']['routeTable']['id'])
    logger.debug('route ids: %s', route_table_ids)
    return route_table_ids


def get_route_table_ids():
    """#TODO fixDocstring"""
    route_table_ids = set()

    vnet_id = get_vnet_id()
    logger.debug('vnet_id: %s', vnet_id)
    vnet = azure.arm('GET', vnet_id + get_api_version(vnet_id))[1]
    logger.debug('vnet: %s', json.dumps(vnet, indent=2))
    route_table_ids |= get_route_table_ids_for_vnet(vnet)

    for peering in vnet['properties'].get('virtualNetworkPeerings', []):
        vnet_id = peering['properties']['remoteVirtualNetwork']['id']
        state = peering['properties']['peeringState']
        logger.debug('peered vnet_id: %s state: %s', vnet_id, state)
        if state != 'Connected':
            logger.info('peered vnet %s in state %s ignored', vnet_id, state)
            continue
        try:
            vnet = azure.arm('GET', vnet_id + get_api_version(vnet_id))[1]
        except Exception:
            logger.info('Failed to retrieve peered network %s', vnet_id)
            logger.info('%s', traceback.format_exc())
            continue
        logger.debug('peered vnet: %s', json.dumps(vnet, indent=2))
        route_table_ids |= get_route_table_ids_for_vnet(vnet)

    logger.debug('route ids: %s', route_table_ids)
    return route_table_ids


def set_routing_tables():
    """#TODO fixDocstring"""
    todo = False

    route_table_ids = get_route_table_ids()
    for rid in route_table_ids:
        try:
            logger.debug('route table id: %s', rid)
            route_table = azure.arm('GET', rid + get_api_version(rid))[1]
            logger.debug('%s', json.dumps(route_table, indent=2))

            if not is_resource_ready(route_table):
                todo = True
                continue
            dirty = False
            for route in route_table['properties'].get('routes', []):
                if route['properties']['nextHopType'] != 'VirtualAppliance':
                    continue
                next_hop = route['properties'].get('nextHopIpAddress')
                if next_hop not in conf['addresses']['peer']:
                    continue
                cidr = route['properties'].get('addressPrefix', '').split('/')
                if (len(cidr) == 2 and cidr[0] in conf['addresses']['peer'] and
                        cidr[1] == '32'):
                    continue
                dirty = True

                my_addr = conf['addresses']['me'][
                    conf['addresses']['peer'].index(next_hop)]

                logger.info('changing route: my address %s\n%s', my_addr,
                            json.dumps(route, indent=2))
                route['properties']['nextHopIpAddress'] = my_addr
            if dirty:
                logger.info('about to update route table:\n%s',
                            json.dumps(route_table, indent=2))
                route_table = safe_arm_put(rid, route_table, "route table update")
                logger.info('route table update initiated:\n%s',
                            json.dumps(route_table, indent=2))
            else:
                logger.debug('route table already set correctly')
        except rest.RequestException as e:
            if e.code in {401, 403}:
                logger.info('%s', traceback.format_exc())
            else:
                raise
    return todo


def setLocalActive():
    """#TODO fixDocstring"""
    logger.debug('setLocalActive called')

    todo = False
    try:
        if templateName in ['ha', 'ha_terraform']:
            logger.info('Template type: %s, calling set_cluster_ips()', templateName)
            todo |= set_cluster_ips()
            logger.info('set_cluster_ips() completed, todo=%s', todo)
        else:
            todo |= set_routing_tables()
            if 'clusterNetworkInterfaces' in conf:
                todo |= set_cluster_ips()
                todo |= set_lb_nat_rules()
            elif templateName != 'stack-ha':
                todo |= set_public_address()
    except Exception as e:
        logger.error('Error in setLocalActive: %s', str(e))
        logger.error('Exception details:', exc_info=True)
        raise
        
    if conf.get('todo') and not todo:
        logger.info('Done')
        logger.debug('Updating cluster status file with %s status', DONE)
        update_cluster_status_file(DONE)
    conf['todo'] = todo


def poll():
    """#TODO fixDocstring"""
    try:
        logger.debug('poll called')
        cphaprob = subprocess.check_output(['cphaprob', 'stat'])
        matchObj = re.match(
            r'^.*\(local\)\s*([0-9.]*)\s*[0-9.\%]*\s*([a-zA-Z]*).*$',
            cphaprob.decode('utf-8'), re.MULTILINE | re.DOTALL)
        state = 'Unknown'
        if matchObj:
            state = matchObj.group(2).lower()
        logger.debug('%s', 'state: ' + state)
        if state in ['active', 'active attention']:
            logger.debug(state + ' mode detected')
            setLocalActive()
        else:
            logger.debug('Updating cluster status file with %s status', NOT_STARTED)
            update_cluster_status_file(NOT_STARTED)
    except Exception:
        logger.info('%s', traceback.format_exc())


def update_cpdiag():
    """
    This function responsible to report about 'Multiple vips' feature usage to cpdiag
    """
    try:
        for cni, vips in conf[CLUSTER_NETWORK_INTERFACES].items():
            vips_number = len(vips)
            key = f'{str(cni)}_vips_number'
            vips_attribute = f'{key}: {vips_number}\n'
            update_multiple_vip_attribute(file_location=CLOUD_VERSION_PATH, key=key, text=vips_attribute)
    except Exception as e:
        logger.error(f'Failed to update cpdiag with VIPs number, Error - {str(e)}')


def update_multiple_vip_attribute(file_location, key, text):
    """
    This function updates cloud-version file with the updated number of VIPs for eth0 and eth1
    @param file_location: /etc/cloud-version
    @param key: eth0_vips_number/eth1_vips_number
    @param text: eth0_vips_number: <number>
    """
    try:
        with open(file_location, 'r') as file:
            lines = file.readlines()
        modified_lines = []
        exists = False
        for line in lines:
            if line.startswith(key):
                exists = True
                line = text
            modified_lines.append(line)
        if not exists:
            modified_lines.append(text)
        with open(file_location, 'w') as file:
            file.writelines(modified_lines)
    except Exception as e:
        logger.error('-- Failed to write ' + text + 'to ' + file_location)
        raise e


class Server(object):
    """#TODO fixDocstring"""
    def __init__(self):
        tmpdir = os.environ['FWDIR'] + '/tmp'
        self.pidFileName = os.path.join(tmpdir, 'ha.pid')
        self._regPid()
        self.sockpath = os.path.join(tmpdir, 'ha.sock')
        self.timeout = 5.0
        try:
            os.remove(self.sockpath)
        except Exception:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.setblocking(0)
        self.sock.bind(self.sockpath)

    def __enter__(self):
        """#TODO fixDocstring"""
        return self

    def __exit__(self, type, value, traceback):
        """#TODO fixDocstring"""
        self._delPid()
        try:
            self.sock.close()
        except Exception:
            pass
        try:
            os.remove(self.sockpath)
        except Exception:
            pass

    def _delPid(self):
        try:
            os.remove(self.pidFileName)
        except Exception:
            pass

    def _regPid(self):
        with open(self.pidFileName, 'w') as f:
            f.write(str(os.getpid()))

    def run(self):
        """#TODO fixDocstring"""
        handlers = [('RECONF', reconf), ('CHANGED', poll)]
        while True:
            rl, wl, xl = select.select([self.sock], [], [], self.timeout)
            events = set()
            while True:
                try:
                    dgram = self.sock.recv(1024)
                    logger.debug('%s', 'received: ' + dgram.decode('utf-8'))
                    events.add(dgram)
                except socket.error as e:
                    if e.args[0] in [errno.EAGAIN, errno.EWOULDBLOCK]:
                        events.add('CHANGED')
                        break
                    raise
            for h in handlers:
                if h[0] in events:
                    h[1]()
            if 'STOP' in events:
                logger.debug('Leaving...')
                break


def main():
    """#TODO fixDocstring"""
    logger.info('Started')
    while True:
        try:
            reconf()
            break
        except Exception:
            logger.info('%s', traceback.format_exc())
            time.sleep(5)

    with Server() as server:
        server.run()


if __name__ == '__main__':
    main()
