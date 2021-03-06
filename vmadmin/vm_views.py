#coding=utf-8
import uuid
import json
import re
from django.shortcuts import render
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse

from django.contrib.auth.decorators import login_required
from .auth import staff_required

from utils.page import get_page
from django.conf import settings

from api.vm import get_list as api_vm_get_list
from api.vm import status as api_vm_status
from api.vm import op as api_vm_op
from api.vm import edit as api_vm_edit
from api.vm import create as api_vm_create
from api.vm import get as api_vm_get
from api.vm import migrate as api_vm_migrate
from api.vm import reset as api_vm_reset
from api.vm import get_snap_list as api_vm_get_snap_list
from api.vm import create_snap as api_vm_create_snap
from api.vm import rollback_snap as api_vm_rollback_snap
from api.vm import set_snap_remarks as api_vm_set_snap_remarks

from api.center import get_list as api_center_get_list
from api.group import get_list as api_group_get_list
from api.host import get_list as api_host_get_list
from api.host import get as api_host_get
from api.images import get_list as api_image_get_list
from api.images import get_type_list as api_image_get_type_list
from api.ceph import get_list as api_ceph_get_list
from api.net import get_vlan_list as api_net_get_vlan_list
from api.net import get_vlan as api_net_get_vlan
from api.net import get_vlan_type_list as api_net_get_vlan_type_list
from api.net import get_vlan_ip_list as api_net_get_vlan_ip_list
from api.vnc import open as api_vnc_open
from api.error import ERROR_CN
from api.volume import get_list as api_volume_get_list

from .view_tools import get_vm_list_by_center
from .view_tools import vm_list_sort
from .view_tools import image_list_sort
from .view_tools import vlan_list_sort

@login_required
def index_view(req):
    return HttpResponseRedirect('/vmadmin/vm/list/')

@login_required
def vm_list_view(req):
    dicts = {}
    
    #获取GET参数
    arg_center = req.GET.get('center')
    arg_group = req.GET.get('group')
    arg_host = req.GET.get('host')
    arg_ip = req.GET.get('ip')
    arg_creator = req.GET.get('creator')
    arg_text = req.GET.get('text')
    
    #参数校验
    if arg_center:
        try:
            arg_center = int(arg_center)
        except:
            arg_center = None
    if arg_group:
        try:
            arg_group = int(arg_group)
        except:
            arg_group = None
    if arg_host:
        try:
            arg_host = int(arg_host)
        except:
            arg_host = None
    if arg_ip:
        arg_ip = arg_ip.strip()
    if arg_text:
        arg_text = arg_text.strip() 
    
    #获取分中心列表
    center_info = api_center_get_list({'req_user': req.user})
    if center_info['res']:
        dicts['center_list'] = center_info['list']
    else:
        dicts['center_list'] = []
    
    #根据分中心获取集群列表
    if arg_center:
        group_info = api_group_get_list({'req_user': req.user, 'center_id': arg_center})
        if group_info['res']:
            dicts['group_list'] = group_info['list']
    
    #根据集群获取宿主机列表
    if arg_group:
        host_info = api_host_get_list({'req_user': req.user, 'group_id': arg_group})
        if host_info['res']:
            dicts['host_list'] = host_info['list']
            
    #虚拟机列表筛选
    vm_list = []
    
    #根据主机筛选
    if arg_host and arg_group and arg_center:
        vms_info = api_vm_get_list({'req_user': req.user, 'group_id': arg_group})
        if vms_info['res']:
            for vm in vms_info['list']:
                if vm['host_id'] == int(arg_host):
                    vm_list.append(vm)
    
    #根据集群筛选
    elif arg_group and arg_center:
        vms_info = api_vm_get_list({'req_user': req.user, 'group_id': arg_group})
        if vms_info['res']:
            vm_list = vms_info['list']
    
    #根据分中心筛选
    elif arg_center:
        vm_list = get_vm_list_by_center(req.user, arg_center)
    else:
        for center in dicts['center_list']:
            vm_list += get_vm_list_by_center(req.user, center['id'])
    
    #从虚拟机列表中获取创建者集合
    creator_dic = {}
    for vm in vm_list:
        if vm['creator'] not in creator_dic:
            creator_dic[vm['creator']] = 1
    dicts['creator_list'] = list(creator_dic.keys())
              
    #根据创建者筛选
    if arg_creator:
        i = 0
        l = len(vm_list)
        while True:
            if i >= l:
                break
            if vm_list[i]['creator'] != arg_creator:
                del(vm_list[i])
                l -= 1
            else:
                i += 1
    
    #根据ip地址筛选
    if arg_ip:
        for i in range(len(vm_list)-1,-1,-1): #反向循环，删除列表中不合要求项 by hai
            if vm_list[i]['ipv4'].find(arg_ip) == -1: del(vm_list[i])

    #根据 主机编号-ip-备注 综合筛选
    if arg_text:
        for i in range(len(vm_list)-1,-1,-1): #反向循环，删除列表中不合要求项 
            if vm_list[i]['ipv4'].find(arg_text) == -1: 
                if vm_list[i]['remarks'].find(arg_text) == -1: 
                    if vm_list[i]['uuid'].find(arg_text) == -1: 
                        del(vm_list[i])
    
    vm_list = vm_list_sort(vm_list)
    
    dicts['p'] = get_page(vm_list, req)
    for vm in dicts['p'].object_list:
        vm['can_operate'] = req.user.is_superuser or vm['creator'] == req.user.username
        res = api_volume_get_list({'req_user': req.user, 'vm_uuid': vm['uuid']})
        if res['res']:
            vm['volumes'] = res['list']
        else:
            vm['volumes'] = []

    return render(req, 'vmadmin_list.html', dicts)

@login_required
def vm_create_view(req):
    dicts = {}
    
    center_dic = api_center_get_list({'req_user': req.user})
    if center_dic['res']:
        dicts['center_list'] = center_dic['list']
    
    arg_center = req.GET.get('center')    
    if not arg_center and len(dicts['center_list']) > 0:
        arg_center = dicts['center_list'][0]['id']
    if arg_center:
        #创建虚拟机
        #by lzx: 把post处理放在获取渲染页面数据的操作之前，以使得获取准确的用于渲染html的数据
        if req.method == 'POST':
            arg_group = req.POST.get('group')
            arg_host = req.POST.get('host')
            arg_image = req.POST.get('image')
            arg_net = req.POST.get('net')
            arg_vlan = req.POST.get('vlan')
            arg_ip = req.POST.get('ip')
            arg_vcpu = req.POST.get('vcpu')
            arg_mem = req.POST.get('mem')
            arg_num = req.POST.get('num')
            arg_remarks = req.POST.get('remarks')
            
            posted_data = { 'group':arg_group,'host':arg_host,'image':arg_image,
                            'net':arg_net,'vlan':arg_vlan,'ip':arg_ip,'vcpu':arg_vcpu,
                            'mem':arg_mem,'num':arg_num,'remarks':arg_remarks}
            try:
                dicts['posted_data_json'] = json.dumps(posted_data)
            except Exception as e:
                dicts['posted_data_json'] = json.dumps(None)
                print(e)
            res = []
            if (arg_group and arg_group.isdigit() 
                and arg_image and arg_image.isdigit() 
                and arg_vcpu and arg_vcpu.isdigit() 
                and arg_mem and arg_mem.isdigit() 
                and arg_num and arg_num.isdigit()):
                if int(arg_num) > 1:
                    arg_ip = None
                for i in range(int(arg_num)):
                    create_res = api_vm_create({
                        'req_user': req.user,
                        'group_id': arg_group,
                        'host_id': arg_host,
                        'image_id': arg_image,
                        'net_type_id': arg_net,
                        'vlan_id': arg_vlan,
                        'vcpu': arg_vcpu,
                        'mem': arg_mem,
                        'remarks': arg_remarks,
                        'ipv4': arg_ip or None})
                    if create_res['res'] == False:
                        if create_res['err'] in ERROR_CN:
                            create_res['error'] = ERROR_CN[create_res['err']]
                        else:
                            create_res['error'] = create_res['err']
                    res.append(create_res)
                dicts['res'] = res
            else:
                dicts['error'] = '参数错误。'

        #获取集群列表
        group_dic = api_group_get_list({'req_user': req.user, 'center_id': arg_center})
        if group_dic['res']:
            dicts['group_list'] = group_dic['list']
        else:
            dicts['group_list'] = []

        #获取宿主机列表
        hosts = {}
        for g in dicts['group_list']:
            host_dic = api_host_get_list({'req_user': req.user, 'group_id': g['id']})
            if host_dic['res']:
                # hosts[g['id']] = host_dic['list']
                hosts[g['id']] = []
                for host in host_dic['list']:
                    if host['enable']:
                        hosts[g['id']].append(host)
        dicts['hosts_json'] = json.dumps(hosts)
            
        #获取镜像列表
        image_dic = {}
        cephpool_dic = api_ceph_get_list({'req_user': req.user, 'center_id': arg_center})
        if cephpool_dic['res']:            
            for cephpool in cephpool_dic['list']:
                image_res = api_image_get_list({'req_user': req.user, 'ceph_id': cephpool['id'], 'enable': True})
                if image_res['res']:
                    for image in image_res['list']:
                        if image['type'] in image_dic:
                            image_dic[image['type']].append(image)
                        else:
                            image_dic[image['type']] = [image]
        image_type_list_info = api_image_get_type_list()
        if image_type_list_info['res']:
            image_type_list = [t['name'] for t in image_type_list_info['list']]
        else:
            image_type_list = list(image_dic.keys())
        image_list_ordered = []
        for image_type in image_type_list:
            if image_type in image_dic:
                image_list_ordered.append((image_type, image_list_sort(image_dic[image_type])))
        
        dicts['image_list_ordered'] = image_list_ordered
        
        #获取网络类型
        vlan_type_dic = {}
        vlans = {}
        vlan_ip_dic = {}
        for group in dicts['group_list']:
            if group['id'] not in vlans:
                vlans[group['id']] = {}
            vlan_dic = api_net_get_vlan_list({'req_user': req.user, 'group_id': group['id']})
            if vlan_dic['res']:
                #vlan sorting
                vlan_list = vlan_list_sort(vlan_dic['list'])
                for vlan in vlan_list:
                    if vlan['type_code'] not in vlan_type_dic:
                        vlan_type_dic[vlan['type_code']] = vlan['type']
                    if vlan['type_code'] not in vlans[group['id']]:
                        vlans[group['id']][vlan['type_code']] = [vlan]
                    else:
                        vlans[group['id']][vlan['type_code']].append(vlan)
                    
                    macip_info = api_net_get_vlan_ip_list({'vlan_id':vlan['id'], 'req_user': req.user})
                    if macip_info['res']:
                        vlan_ip_dic[vlan['id']] = [macip['ipv4'] for macip in macip_info['list'] 
                            if (macip['vmid'] == "" or macip['vmid'] is None) and macip['enable'] is True]

        #VLAN_type sorting
        vlan_type_list_info = api_net_get_vlan_type_list({'req_user': req.user})
        if vlan_type_list_info['res']:
            vlan_type_list = [(t['code'], t['name']) for t in vlan_type_list_info['list'] if t['code'] in vlan_type_dic]
        else:
            vlan_type_list = [(t[0], t[1]) for t in list(vlan_type_dic.items())]
        dicts['vlan_type_list'] = vlan_type_list
        print(vlan_type_list_info)
        dicts['vlans_json'] = json.dumps(vlans)

        # 各个vlan的可用ip列表
        dicts['vlan_ip_json'] = json.dumps(vlan_ip_dic)        
            
    #return render_to_response('vmadmin_create.html', dicts, context_instance=RequestContext(req))
    return render(req,'vmadmin_create.html', dicts)

@login_required
def vm_edit_view(req):
    dicts = {}
    arg_vmid = req.GET.get('vmid')
    
    if req.method == 'POST':
        arg_cpu = req.POST.get('cpu')
        arg_mem = req.POST.get('mem')
        
        status_res = api_vm_status({'req_user': req.user, 'uuid': arg_vmid})
        
        if status_res['res'] and status_res['status'] != 1:
            if arg_cpu.isdigit() and arg_mem.isdigit():
                edit_res = api_vm_edit({'req_user': req.user,
                                        'uuid': arg_vmid,
                                        'vcpu': arg_cpu, 
                                        'mem': arg_mem})
                if not edit_res['res']:
                    dicts['warning'] = '修改失败。'
        else:
            dicts['warning'] = '只能修改处于关机状态的虚拟机。'
            
    obj_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    if obj_res['res']:
        obj = obj_res['info']
    else:
        return HttpResponseRedirect('../list/')
    dicts['vmobj'] = obj
    
    host_res = api_host_get({'req_user': req.user, 'host_id': obj['host_id']})
    if host_res['res']:
        host = host_res['info']
        dicts['remain_mem'] = host['mem_total'] - \
                              host['mem_allocated'] - \
                              host['mem_reserved']   
        if dicts['remain_mem'] < 0:
            dicts['remain_mem'] = 0
        dicts['remain_cpu'] = host['vcpu_total'] - host['vcpu_allocated']
        if dicts['remain_cpu'] < 0:
            dicts['remain_cpu'] = 0
    
    #return render_to_response('vmadmin_edit.html', dicts, context_instance=RequestContext(req))
    return render(req,'vmadmin_edit.html', dicts)

@login_required
def vm_vnc_view(req):
    arg_vmid = req.GET.get('vmid')
    url_res = api_vnc_open({'req_user': req.user, 'uuid': arg_vmid})
    if settings.DEBUG: print(url_res)
    if url_res['res']:
        return HttpResponseRedirect(url_res['url'])
    return HttpResponse('vnc链接获取失败。')

@login_required
def vm_detail_view(req):
    arg_vmid = req.GET.get('vmid')
    vm_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    dicts = {}
    if vm_res['res']:
        dicts['vmobj'] = vm_res['info']
        vlan = api_net_get_vlan({'req_user': req.user, 'vlan_id': dicts['vmobj']['vlan_id']})
        if vlan['res']:
            dicts['vmobj']['br'] = vlan['info']['br']

        # 添加操作功能和挂载云硬盘 2018-07-12 yanghao
        dicts['vmobj']['can_operate'] = req.user.is_superuser or dicts['vmobj']['creator'] == req.user.username

        from api.volume import get_volume_available
        volume_info = get_volume_available({'req_user': req.user,'group_id':dicts['vmobj']['group_id'],'vm_uuid':dicts['vmobj']['uuid']})
        # volume_info = api_volume_get_list({'req_user': req.user,'group_id':dicts['vmobj']['group_id']})
        ret_list = []
        if volume_info['res']:
            ret_list += volume_info['list']
        dicts['p'] = get_page(ret_list, req)

        #添加 快照信息 2018-10-08 lzx
        snap_res = api_vm_get_snap_list({'req_user': req.user, 'uuid': dicts['vmobj']['uuid']})    
        dicts['snap_list'] = []
        if snap_res['res']:
            dicts['snap_list'] = snap_res['list']
        
    else:
        if settings.DEBUG: print(vm_res['err'])
        return HttpResponseRedirect('../list/')
    return render(req,'vmadmin_detail.html', dicts)
    #return render_to_response('vmadmin_detail.html', dicts, context_instance=RequestContext(req))

@login_required   
def vm_migrate_view(req):
    dicts = {}
    arg_vmid = req.GET.get('vmid')
    if req.method == 'POST':
        arg_vmid = req.POST.get('vmid')
        arg_host = req.POST.get('host')
        status_res = api_vm_status({'req_user': req.user, 'uuid': arg_vmid})
        if status_res['res'] and not status_res['status'] in (1, 2, 3, 7):
            migrate_res = api_vm_migrate({'req_user': req.user, 'uuid': arg_vmid, 'host_id': arg_host})
            if migrate_res['res']:
                dicts['result'] = '迁移成功。'
            else:
                err_msg = ERROR_CN[migrate_res['err']] if  migrate_res['err'] in ERROR_CN else  migrate_res['err']
                dicts['result'] = '迁移失败: %s' % err_msg
        else:
            dicts['result'] = '迁移失败：只能在关机状态迁移。'
            
    vm_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    
    if vm_res['res']:
        dicts['vmobj'] = vm_res['info']
    else:
        return HttpResponseRedirect(reverse("vm_list"))
    
    group_res = api_group_get_list({'req_user': req.user, 'center_id': dicts['vmobj']['center_id']})
    if group_res['res']:
        host_list = []
        for group in group_res['list']:
            host_res = api_host_get_list({'req_user': req.user, 'group_id': group['id']})
            if host_res['res']:
                for host in host_res['list']:
                    if dicts['vmobj']['host_id'] == host['id'] or host['enable'] == False:
                        continue
                    host['group_name'] = group['name']
                    host_list.append(host)
        dicts['host_list'] = host_list
    return render(req,'vmadmin_migrate.html', dicts)


@login_required   
def vm_reset_view(req):
    dicts = {}
    arg_vmid = req.GET.get('vmid')
    if req.method == 'POST':
        arg_vmid = req.POST.get('vmid')
        arg_image = req.POST.get('image')
        status_res = api_vm_status({'req_user': req.user, 'uuid': arg_vmid})
        if status_res['res'] and not status_res['status'] in (1, 2, 3, 7):
            reset_res = api_vm_reset({'req_user': req.user, 'uuid': arg_vmid, 'image_id': arg_image})
            if reset_res['res']:
                dicts['result'] = '重置成功。'
            else:
                err_msg = ERROR_CN[reset_res['err']] if  reset_res['err'] in ERROR_CN else  reset_res['err']
                dicts['result'] = '重置失败: %s' % err_msg
                
        else:
            dicts['result'] = '重置失败：只能在关机状态重置。'
            
    vm_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    
    if vm_res['res']:
        dicts['vmobj'] = vm_res['info']
    else:
        return HttpResponseRedirect(reverse("vm_list"))
    
    image_res = api_image_get_list({'req_user': req.user, 'ceph_id': dicts['vmobj']['ceph_id'], 'enable': True})
    image_dic = {}
    if image_res['res']:
        for image in image_res['list']:
            if image['type'] in image_dic:
                image_dic[image['type']].append(image)
            else:
                image_dic[image['type']] = [image]

    image_type_list_info = api_image_get_type_list()
    if image_type_list_info['res']:
        image_type_list = [t['name'] for t in image_type_list_info['list']]
    else:
        image_type_list = list(image_dic.keys())
    image_list_ordered = []
    for image_type in image_type_list:
        if image_type in image_dic:
            image_list_ordered.append((image_type, image_list_sort(image_dic[image_type])))
    dicts['image_list_ordered'] = image_list_ordered

    return render(req,'vmadmin_reset.html', dicts)

@login_required
def vm_status_ajax(req):
    vmid = req.POST.get('vmid')
    status = api_vm_status({'req_user': req.user, 'uuid': vmid})
    if status['res']:
        status['vmid'] = vmid
    else:
        if status['err'] in ERROR_CN:
            status['error'] = ERROR_CN[status['err']] 
    return HttpResponse(json.dumps(status), content_type='application/json')

@login_required
def vm_op_ajax(req):
    vmid = req.POST.get('vmid')
    op = req.POST.get('op')
    res = api_vm_op({
        'req_user': req.user,
        'uuid': vmid,
        'op': op})
    if not res['res'] and res['err'] in ERROR_CN:
        res['error'] = ERROR_CN[res['err']]
    return HttpResponse(json.dumps(res), content_type='application/json')

@login_required
def vm_batch_op_ajax(req):
    vmid_list = req.POST.getlist('vmid_list[]')
    op = req.POST.get('op')
    res_list = []
    for vmid in vmid_list:
        res = api_vm_op({
            'req_user': req.user,
            'uuid': vmid,
            'op': op})
        if not res['res'] and res['err'] in ERROR_CN:
            res['error'] = ERROR_CN[res['err']]
        res['vmid'] = vmid
        res_list.append(res)
    return HttpResponse(json.dumps(res_list), content_type='application/json')

@login_required
def vm_edit_remarks_ajax(req):
    remarks = req.POST.get('remarks')
    vmid = req.POST.get('vmid')
    res = api_vm_edit({
                       'req_user': req.user,
                       'uuid': vmid, 
                       'remarks': remarks})
    if not res['res'] and res['err'] in ERROR_CN:
        res['error'] = ERROR_CN[res['err']]
    return HttpResponse(json.dumps(res), content_type='application/json')



@login_required
def vm_snap_create_view(req):
    arg_vmid = req.GET.get('vmid')
    obj_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    if obj_res['res']:
        obj = obj_res['info']
    else:
        return HttpResponseRedirect('/vmadmin/vm/list/')

    dicts = {}
    if req.method == 'POST':
        group_id = obj['group_id']
        remarks = req.POST.get('remarks', None)
        
        create_res = api_vm_create_snap({'req_user': req.user,'uuid':arg_vmid,'remarks':remarks})

        if create_res['res']:
            dicts['alert_msg'] = "快照创建成功"
        else:
            err_msg = ERROR_CN[create_res['err']] if  create_res['err'] in ERROR_CN else  create_res['err']
            dicts['alert_msg'] = '快照创建失败: %s' % err_msg

    dicts['vmobj'] = obj

    return render(req, 'vmadmin_snap_create.html', dicts)

# @login_required   
# def vm_snap_list_view(req):
#     dicts = {}
#     arg_vmid = req.GET.get('vmid',None)

#     vm_res = api_vm_get({'req_user': req.user, 'uuid': arg_vmid})
    
#     if vm_res['res']:
#         dicts['vmobj'] = vm_res['info']
#     else:
#         return HttpResponseRedirect(reverse("vm_list"))
    
#     snap_res = api_vm_get_snap_list({'req_user': req.user, 'uuid': dicts['vmobj']['uuid']})
    
#     dicts['snap_list'] = []
#     if snap_res['res']:
#         dicts['snap_list'] = snap_res['list']

#     return render(req,'vmadmin_snap_list.html', dicts)


@login_required
def vm_snap_rollback_ajax_view(req):
    vmid = req.POST.get('vmid', None)
    snap_id = req.POST.get('snap_id', None)

    dicts = {}
    dicts['res'] = False
    status_res = api_vm_status({'req_user': req.user, 'uuid': vmid})
    if status_res['res'] and status_res['status'] != 1:
        rollback_res = api_vm_rollback_snap({'req_user': req.user,'uuid': vmid,'snap_id': snap_id})
        if rollback_res['res']:
            dicts['res'] = True
        else:
            err_msg = ERROR_CN[rollback_res['err']] if  rollback_res['err'] in ERROR_CN else  rollback_res['err']
            dicts['error'] = '快照回滚失败: %s' % err_msg            
    else:
        dicts['error'] = '快照回滚失败：只能在关机状态执行回滚操作。'
    
    return HttpResponse(json.dumps(dicts), content_type='application/json')


@login_required
def vm_snap_edit_remarks_ajax(req):
    vmid = req.POST.get('vmid')
    snap_id = req.POST.get('snap_id')
    remarks = req.POST.get('remarks')
    res = api_vm_set_snap_remarks({
                       'req_user': req.user,
                       'uuid': vmid, 
                       'snap_id': snap_id, 
                       'remarks': remarks})
    if not res['res'] and res['err'] in ERROR_CN:
        res['error'] = ERROR_CN[res['err']]
    return HttpResponse(json.dumps(res), content_type='application/json')