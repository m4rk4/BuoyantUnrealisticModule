import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, save_debug=False):
    # https://hudsonhubtimes-oh.newsmemory.com/?selDate=20220612&goTo=A01&artid=5
    return None


def get_feed(args, save_debug=False):
    # https://hudsonhubtimes-oh.newsmemory.com/
    # https://hudsonhubtimes-oh.newsmemory.com/eebrowser/ipad/html5.check.22033014/ajax-request.php?pSetup=hudsonhubtimes&preview=1&cc=1&action=issues&maxIssues=14&prefEdi=Hudson%20Hub%20Times
    split_url = urlsplit(args['url'])
    edition = split_url.netloc.split('.')[0]
    sites_json = utils.read_json_file('./sites.json')
    edition_json = sites_json['newsmemory'][edition]
    issues_url = 'https://{}/eebrowser/ipad/html5.check.22033014/ajax-request.php?pSetup={}&preview=1&cc=1&action=issues&maxIssues=7&prefEdi={}'.format(split_url.netloc, edition_json['pSetup'], quote_plus(edition_json['title']))
    issues_json = utils.get_url_json(issues_url)
    if not issues_json:
        return None
    if save_debug:
        utils.write_file(issues_json, './debug/feed.json')

    pages_url = 'https://{}/eebrowser/ipad/html5.check.22033014/ajax-request.php?pSetup={}&preview=1&action=sql-remote&operationSQL=pagesAndIssueByIssueAndPaperAndEdition&issue={}&paper={}&edition={}&editionForDB={}'.format(split_url.netloc, edition_json['pSetup'], issues_json[0]['issue'], issues_json[0]['paper'], quote_plus(issues_json[0]['mainEdition']), issues_json[0]['paper'])
    pages_json = utils.get_url_json(pages_url)
    if not pages_json:
        return None
    if save_debug:
        utils.write_file(pages_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    feed['items'] = []

    for page in pages_json['rows']:
        if page['page'].startswith('N'):
            # Skip national news (NN) and sports (NS)
            continue

        articles_url = 'https:{}/eebrowser/ipad/html5.check.22033014/ajax-request.php?pSetup={}&preview=1&cc={}&action=sql-remote&operationSQL=pagesAndArticlesByPageAndXmlId&pageId={}&page={}&xmlId={}&edition={}&paper={}&issue={}&editionForDB={}&mtime=54CC1859'.format(pages_json['serverCDN'], pages_json['siteId'], page['filename'], page['pageId'], page['page'], page['xmlId'], quote_plus(page['edition']), pages_json['siteId'], issues_json[0]['issue'], issues_json[0]['paper'])
        print(articles_url)
        articles_json = utils.get_url_json(articles_url)
        if not articles_json:
            return None
        if save_debug:
            utils.write_file(articles_json, './debug/articles.json')

        for article in articles_json['rows']:
            print(article['type'])
            if article['type'] == 'Advertisement' or article['type'] == 'Page Layout' or article['type'] == 'Singola Colonna':
                continue
            elif article['type'] == 'Graphic' and len(re.findall(r'Seven|Day|Forecast', article['title'])) == 3:
                continue

            pj = json.loads(article['pj'])
            if pj:
                key = next(iter(pj))
                if pj[key].get('from'):
                    continue

            if page['title'] != 'Obituaries':
                item = {}
                item['url'] = 'https://{}?selDate={}&goTo={}&artid={}'.format(split_url.netloc, issues_json[0]['issue'], article['page'], article['xmlId'])
                item['id'] = item['url']
                item['title'] = re.sub(r'[\u0081-\u00a0]', '', article['title'])
            elif 'item' not in locals():
                item = {}
                item['url'] = 'https://{}?selDate={}&goTo={}'.format(split_url.netloc, issues_json[0]['issue'], page['page'])
                item['id'] = item['url']
                item['title'] = re.sub(r'[\u0081-\u00a0]', '', page['title'])

            if not item.get('date_published'):
                dt = datetime.strptime(issues_json[0]['issue'], '%Y%m%d').replace(tzinfo=timezone.utc)
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

            article_html = article['html'].strip()
            article_html = article_html.replace('<br/><hr/>', '')
            article_html = re.sub(r'[\u0081-\u00a0]', '', article_html)
            #article_html = article_html.replace('\u0081', '')
            #article_html = article_html.replace('\u008f', '')
            soup = BeautifulSoup(article_html, 'html.parser')

            for el in soup.find_all(id=re.compile(r'articleAds')):
                el.decompose()

            for el in soup.find_all(class_='maintitle'):
                el.decompose()

            for el in soup.find_all('span', class_=re.compile(r'Fid_\d+')):
                el.unwrap()

            if pj:
                for el in soup.find_all('p', text=re.compile(r'See {}[^,]*, Page'.format(key))):
                    el.decompose()
                for el in soup.find_all('p', text=re.compile(r'Continued from Page')):
                    el.decompose()

            item['author'] = {"name": "TODO"}
            if item.get('content_html'):
                item['content_html'] += str(soup)
            else:
                item['content_html'] = str(soup)

            if page['title'] != 'Obituaries':
                feed['items'].append(item)
                del item

        if page['title'] == 'Obituaries':
            feed['items'].append(item)
            del item
    return feed