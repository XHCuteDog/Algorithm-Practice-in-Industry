
'''
credit to original author: Glenn (chenluda01@outlook.com)
Author: Doragd
'''

import os
import requests
import time
import json
import datetime
from tqdm import tqdm
from translate import translate

# 用于转发到飞书群组
SERVERCHAN_API_KEY = os.environ.get("SERVERCHAN_API_KEY", None)
# 搜索关键词
QUERY = os.environ.get('QUERY', 'cs.IR')
# 搜索条数
LIMITS = int(os.environ.get('LIMITS', 3))
# 飞书群组webhook
FEISHU_URL = os.environ.get("FEISHU_URL", None)
# 翻译模型
MODEL_TYPE = os.environ.get("MODEL_TYPE", "DeepSeek")

NOT_SAVE = os.environ.get("NOTSAVE", None)

def get_yesterday():
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')


def search_arxiv_papers(search_term, max_results=10):
    papers = []
    
    # arxiv API docurl[https://info.arxiv.org/help/api/user-manual.html#_calling_the_api]
    url = f'http://export.arxiv.org/api/query?' + \
          f'search_query=all:{search_term}' +  \
          f'&start=0&&max_results={max_results}' + \
          f'&sortBy=submittedDate&sortOrder=descending'

    response = requests.get(url)

    if response.status_code != 200:
        return []

    feed = response.text
    
    
    entries = feed.split('<entry>')[1:]

    if not entries:
        return []

    print('[+] 开始处理每日最新论文....')

    for entry in entries:

        title = entry.split('<title>')[1].split('</title>')[0].strip()
        summary = entry.split('<summary>')[1].split('</summary>')[0].strip().replace('\n', ' ').replace('\r', '')
        url = entry.split('<id>')[1].split('</id>')[0].strip()
        authors = entry.split('<author>')[1].split('</author>')[0].strip()
        # 此时，authors 是一个由多个 <name> name </name> 组成的字符串，需要将其转换为列表，需要从每个 <name> name </name> 中提取出 name
        author_list = [author.split('</name>')[0].strip() for author in authors.split('<name>') if author.strip()]
        pub_date = entry.split('<published>')[1].split('</published>')[0]
        pub_date = datetime.datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d")

        papers.append({
            'title': title,
            'url': url,
            'pub_date': pub_date,
            'author': author_list,
            'summary': summary,
            'translated': '',
        })
    
    print('[+] 开始翻译每日最新论文并缓存....')

    papers = save_and_translate(papers)
    
    return papers


def send_wechat_message(title, content, SERVERCHAN_API_KEY):
    url = f'https://sctapi.ftqq.com/{SERVERCHAN_API_KEY}.send'
    params = {
        'title': title,
        'desp': content,
    }
    requests.post(url, params=params)

def send_feishu_message(title, content, url=FEISHU_URL):
    card_data = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "template": "green",
            "title": {
            "tag": "plain_text",
            "content": title
            }
        },
        "elements": [
            {
            "tag": "img",
            "img_key": "img_v2_9781afeb-279d-4a05-8736-1dff05e19dbg",
            "alt": {
                "tag": "plain_text",
                "content": ""
            },
            "mode": "fit_horizontal",
            "preview": True
            },
            {
            "tag": "markdown",
            "content": content
            }
        ]
    }
    card = json.dumps(card_data)
    body =json.dumps({"msg_type": "interactive","card":card})
    headers = {"Content-Type":"application/json"}
    requests.post(url=url, data=body, headers=headers)


def save_and_translate(papers, filename='arxiv.json'):
    with open(filename, 'r', encoding='utf-8') as f:
        results = json.load(f)

    cached_title2idx = {result['title'].lower():i for i, result in enumerate(results)}
    
    # 存储论文标题
    untranslated_papers = []
    translated_papers = []
    translated_paper_num = 0
    for paper in papers:
        title = paper['title'].lower()
        if title in cached_title2idx.keys():
            translated_papers.append(paper)
            translated_paper_num += 1
            # if NOT_SAVE:
            #     untranslated_papers.append(paper)
        else:
            untranslated_papers.append(paper)
    
    source = []
    for paper in untranslated_papers:
        source.append(paper['summary'])
    target = translate(source)
    assert len(target) == len(untranslated_papers)
    for i in range(len(untranslated_papers)):
        untranslated_papers[i]['translated'] = target[i]

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f'[+] 总检索条数: {len(papers)} | 命中缓存: {translated_paper_num} | 实际返回: {len(untranslated_papers)}....')
    
    untranslated_papers.extend(translated_papers)
    return untranslated_papers

        
def cronjob():

    if SERVERCHAN_API_KEY is None:
        raise Exception("未设置SERVERCHAN_API_KEY环境变量")

    print('[+] 开始执行每日推送任务....')

    yesterday = get_yesterday()
    today = datetime.datetime.now().strftime('%Y-%m-%d')

    print('[+] 开始检索每日最新论文....')
    
    # untranslated papers
    papers = search_arxiv_papers(QUERY, LIMITS)

    if papers == []:
        
        # push_title = f'Arxiv:{QUERY}[X]@{today}'
        send_wechat_message('', '[WARN] NO UPDATE TODAY!', SERVERCHAN_API_KEY)

        print('[+] 每日推送任务执行结束')

        return True
        

    print('[+] 开始推送每日最新论文....')

    for ii, paper in enumerate(tqdm(papers, total=len(papers), desc=f"论文推送进度")):

        title = paper['title']
        url = paper['url']
        pub_date = paper['pub_date']
        summary = paper['summary']
        translated = paper['translated']
        # author = paper['author']

        # yesterday = get_yesterday()

        if pub_date == yesterday:
            msg_title = f'[Newest]{title}' 
        else:
            msg_title = f'{title}'

        msg_url = f'URL: {url}'
        msg_pub_date = f'Pub Date: {pub_date}'
        msg_summary = f'Summary: {summary}'
        msg_translated = f'Translated (Powered by {MODEL_TYPE}):\n\n{translated}'

        push_title = f'Arxiv:{QUERY}[{ii + 1}]@{today}'
        # msg_content = f"[{msg_title}]({url})\n\n{msg_pub_date}\n\n{msg_url}\n\n{msg_translated}\n\n{msg_summary}\n\n"
        msg_content = f"[{msg_title}]({url})\n\n{msg_pub_date}\n\n{msg_url}\n\n{msg_translated}\n\n"
        # send_wechat_message(push_title, msg_content, SERVERCHAN_API_KEY)
        send_feishu_message(push_title, msg_content, FEISHU_URL)

        time.sleep(12)

    print('[+] 每日推送任务执行结束')

    return True


if __name__ == '__main__':
    cronjob()



