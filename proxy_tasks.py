# coding:utf-8

'''
@author = super_fazai
@File    : proxy_tasks.py
@connect : superonesfazai@gmail.com
'''

from celery.utils.log import get_task_logger
from random import choice
from requests import session
from requests.exceptions import (
    ConnectTimeout,
    ProxyError,
    ReadTimeout,
    ConnectionError,
    TooManyRedirects,)
from pickle import dumps
import re

from items import ProxyItem
from settings import (
    CHECK_PROXY_TIMEOUT,
    parser_list,
    proxy_list_key_name,
    high_proxy_list_key_name,
    TEST_HTTP_HEADER,
    start_up_ip_url_list,)
from exception import (
    NotIpException,
)

from fzutils.time_utils import get_shanghai_time
from fzutils.internet_utils import get_random_pc_ua
from fzutils.safe_utils import get_uuid3
from fzutils.celery_utils import init_celery_app
from fzutils.data.pickle_utils import deserializate_pickle_object
from fzutils.sql_utils import BaseRedisCli
from fzutils.common_utils import (
    json_2_dict,
    delete_list_null_str,)
from fzutils.spider.fz_requests import Requests
from fzutils.spider.selector import parse_field
from fzutils.ip_utils import get_ip_address_info

app = init_celery_app()
lg = get_task_logger('proxy_tasks')             # 当前task的logger对象, tasks内部保持使用原生celery log对象
_key = get_uuid3(proxy_list_key_name)           # 存储proxy_list的key
_h_key = get_uuid3(high_proxy_list_key_name)    # 高匿key
redis_cli = BaseRedisCli()
ori_ip_list = []

def _get_base_headers() -> dict:
    return {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': get_random_pc_ua(),
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

@app.task(name='proxy_tasks._get_proxy', bind=True)   # task修饰的方法无法修改类属性
def _get_proxy(self, random_parser_list_item_index, proxy_url) -> list:
    '''
    spiders: 获取代理高匿名ip
    :return:
    '''
    def parse_body(body):
        '''解析url body'''
        def _get_ip(**kwargs) -> str:
            tr = kwargs['tr']
            ip_selector = kwargs['ip_selector']

            ip = parse_field(parser=ip_selector, target_obj=tr)
            assert ip != '', 'ip为空值!'
            ip = re.compile(r'<script .*?</script>').sub('', ip)
            if re.compile('\d+').findall(ip) == []:  # 处理不是ip地址
                raise NotIpException

            lg.info(str(ip))
            ip = re.compile('\d+\.\d+\.\d+\.\d+').findall(ip)[0]
            assert ip != '', 'ip为空值!'

            return ip

        def _get_port(**kwargs) -> str:
            tr = kwargs['tr']
            port_selector = kwargs['port_selector']

            port = parse_field(parser=port_selector, target_obj=tr)
            assert port != '', 'port为空值!'

            return port

        def _get_ip_type(**kwargs) -> str:
            '''获取ip_type'''
            tr = kwargs['tr']
            ip_type_selector = kwargs['ip_type_selector']

            ip_type = parse_field(parser=ip_type_selector, target_obj=tr)
            # 可空
            # assert ip_type != '', 'ip_type为空值!'
            # return 'http' if ip_type == 'HTTP' else 'https'

            return 'http'       # 全部返回'http'

        _ = []
        parser_obj = parser_list[random_parser_list_item_index]
        try:
            part_selector = parser_obj.get('part', {})
            assert part_selector != {}, '获取到part为空值!'
            position = parser_obj.get('position', {})
            assert position != {}, '获取到position为空dict!'
            ip_selector =  position.get('ip', {})
            assert ip_selector != {}, '获取到ip_selector为空dict!'
            port_selector = position.get('port', {})
            assert port_selector != {}, '获取到port_selector为空dict!'
            # 可为None
            ip_type_selector = position.get('ip_type', None)
            # assert ip_type_selector is not None, '获取到ip_type_selector为None!'
        except AssertionError:
            return []

        for tr in parse_field(parser=part_selector, target_obj=body, is_first=False):
            try:
                ip = _get_ip(tr=tr, ip_selector=ip_selector)
                port = _get_port(tr=tr, port_selector=port_selector)
                ip_type = _get_ip_type(tr=tr, ip_type_selector=ip_type_selector)
            except NotIpException:
                continue
            except IndexError:
                lg.error('获取ip时索引异常!跳过!')
                continue
            except (AssertionError, Exception):
                lg.error('遇到错误:', exc_info=True)
                continue

            o = ProxyItem()
            o['ip'] = ip
            try:
                o['port'] = int(port)
            except Exception:
                lg.error('int转换port时出错!跳过!')
                continue
            o['ip_type'] = ip_type
            o['anonymity'] = 1
            o['score'] = 100
            o['last_check_time'] = str(get_shanghai_time())
            # o['country'] = ''
            # o['city'] = ''
            # lg.info('[+] {}:{}'.format(ip, port))
            _.append(dict(o))

        return _

    # 从已抓取的代理中随机代理采集, 没有则用本机ip(first crawl)!
    try:
        encoding = parser_list[random_parser_list_item_index].get('charset')
        proxies = _get_proxies()
        with session() as s:
            response = s.get(
            url=proxy_url,
            headers=_get_base_headers(),
            params=None,
            cookies=None,
            proxies=proxies,
            timeout=CHECK_PROXY_TIMEOUT)
            try:
                body = response.content.decode(encoding)
            except UnicodeDecodeError:
                body = response.text
            body = Requests._wash_html(body)
            # lg.info(body)
    except (ConnectTimeout, ProxyError, ReadTimeout, ConnectionError, TooManyRedirects) as e:
        lg.error('遇到错误: {}'.format(e.args[0]))
        return []
    except Exception:
        lg.error('遇到错误:', exc_info=True)
        return []
    # sleep(2)

    res = parse_body(body)
    if res == []:
        lg.error('html页面解析错误!跳过!')

    return res

def _get_66_ip_list():
    '''
    先获取66高匿名ip
    :return:
    '''
    global ori_ip_list
    params = (
        ('getnum', ''),
        ('isp', '0'),
        ('anonymoustype', '3'),
        ('start', ''),
        ('ports', ''),
        ('export', ''),
        ('ipaddress', ''),
        ('area', '0'),
        ('proxytype', '2'),
        ('api', '66ip'),
    )

    with session() as s:
        try:
            response = s.get('http://www.66ip.cn/nmtq.php', headers=_get_base_headers(), params=params, cookies=None)
        except Exception:
            return []

        body = Requests._wash_html(response.content.decode('gbk'))
    try:
        part = re.compile(r'</script>(.*)</div>').findall(body)[0]
    except IndexError:
        part = ''
    part = re.compile('<script>.*?</script>|</div>.*</div>').sub('', part)
    # print(part)
    ip_list = delete_list_null_str(part.split('<br />'))
    # print(ip_list)
    ori_ip_list = ip_list if ip_list != [] else []

    return ip_list

def get_start_up_ip_list(url):
    '''
    初始抓取时调用
    :param url:
    :return:
    '''
    with session() as s:
        body = s.get(url, headers=_get_base_headers()).text

    if body == '':
        return []
    tmp_ip_list = delete_list_null_str(body.split('\r\n'))

    ip_list = []
    for item in tmp_ip_list:
        try:
            tmp = re.compile('\d+\.\d+\.\d+\.\d+:\d+').findall(item)[0]
            ip_list.append(tmp)
        except IndexError:
            continue

    return ip_list

def _get_proxies() -> dict:
    '''
    随机一个高匿名proxy(极大概率失败, 耐心!)
    :return:
    '''
    global ori_ip_list
    proxy_list = deserializate_pickle_object(redis_cli.get(_h_key) or dumps([]))
    proxies = choice(proxy_list) if len(proxy_list) > 0 else None
    if proxies is not None:
        ip, port = proxies['ip'], proxies['port']
        proxies = {
            'http': 'http://{}:{}'.format(ip, port),
            'https': 'https://{}:{}'.format(ip, port),
        }
        lg.info('正在使用代理 {} crawl...'.format(proxies['http']))
    else:
        if ori_ip_list == []:
            for url in start_up_ip_url_list:
                tmp = get_start_up_ip_list(url)
                ori_ip_list += tmp
            if ori_ip_list == []:
                ori_ip_list = _get_66_ip_list()
                if ori_ip_list == []:
                    lg.info('正在使用本机ip抓取...')

        else:
            pass
        ori_ip_list = list(set(ori_ip_list))
        proxies = {
            'http': 'http://{}'.format(choice(ori_ip_list)),
        }
        lg.info('正在使用代理 {} crawl...'.format(proxies['http']))

    return proxies or {}        # 如果None则返回{}

@app.task(name='proxy_tasks.check_proxy_status', bind=True)    # 一个绑定任务意味着任务函数的第一个参数总是任务实例本身(self)
def check_proxy_status(self, proxy, local_ip, timeout=CHECK_PROXY_TIMEOUT) -> bool:
    '''
    检测代理状态, 突然发现, 免费网站写的信息不靠谱, 还是要自己检测代理的类型
    :param proxy: 待检测代理
    :return:
    '''
    # lg.info(str(self.request))
    res = False
    headers = _get_base_headers()
    proxies = {
        'http': 'http://' + proxy,
        # 'https': 'https://' + proxy,
    }
    try:
        with session() as s:
            response = s.get(url=TEST_HTTP_HEADER, headers=headers, proxies=proxies, timeout=timeout)
            lg.info(str(response.text))
            if response.ok:
                content = json_2_dict(json_str=response.text)
                proxy_connection = content.get('headers', {}).get('Proxy-Connection', None)
                lg.info('Proxy-Connection: {}'.format(proxy_connection))
                ip = content.get('origin', '')
                assert ip != '', 'ip为空!'
                # TODO 老版本的判断 pass
                # if ',' in ip\
                #         or proxy_connection:           # 两个ip, 匿名度: 透明
                #     pass
                # else:                   # 只抓取高匿名代理
                #     if local_ip != ip:
                #         lg.info(str('成功捕获一只高匿ip: {}'.format(proxy)))
                #         return True

                # 新版判断, 新版不用代理请求httpbin返回格式: '原ip, 原ip'
                local_ip_str = '{}, {}'.format(local_ip, local_ip)
                if local_ip_str != ip \
                        and local_ip not in ip:
                    # print(now_ip)
                    lg.info(str('成功捕获一只高匿ip: {}'.format(proxy)))
                    return True
                else:
                    pass

            else:
                pass
    except Exception:
        pass

    return res

@app.task(name='proxy_tasks.get_ip_address_info', bind=True)
def get_ip_address_info(ip:str, timeout=CHECK_PROXY_TIMEOUT) -> dict:
    '''
    获取ip的address信息(国家)
    :param ip:
    :param timeout:
    :return: {} or {'xx': 'xxxx'}
    '''
    try:
        ip_info = get_ip_address_info(ip=ip)
    except Exception as e:
        return {}

    return ip_info