# coding:utf-8

'''
@author = super_fazai
@File    : server.py
@connect : superonesfazai@gmail.com
'''

"""
server端
"""

from flask import (
    Flask,)
from os import getcwd

from api import IpPoolsObj
from settings import SERVER_PORT
from json import dumps
from pprint import pprint

try:
    from gevent.wsgi import WSGIServer      # 高并发部署
except Exception as e:
    from gevent.pywsgi import WSGIServer

app = Flask(__name__, root_path=getcwd())
ip_pools_obj = IpPoolsObj()

@app.route('/', methods=['GET', 'POST'])
def home():
    return '欢迎来到 fz_ip_pool 主页!'

@app.route('/get_all', methods=['GET', 'POST'])
def get_proxy_list():
    '''
    获取代理的接口
    :return:
    '''
    res = []
    all = get_db_old_data()
    for item in all:
        ip = item['ip']
        port = item['port']
        score = item['score']
        check_time = item['last_check_time']

        res.append({
            'ip': ip,
            'port': port,
            'score': score,
            'check_time': check_time,
        })

    return dumps(res)

def get_db_old_data() -> list:
    '''
    获取db数据
    :return:
    '''
    try:    # 先不处理高并发死锁问题
        all = ip_pools_obj._get_all_ip_proxy()
    except Exception:
        print(e)
        return []

    return all

def main():
    print('server 已启动...\nhttp://0.0.0.0:{}\n'.format(SERVER_PORT))
    WSGIServer(listener=('0.0.0.0', SERVER_PORT), application=app).serve_forever()  # 采用高并发部署

if __name__ == '__main__':
    main()
