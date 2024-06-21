import copy, json, math, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    # print_url = url.replace('/show/', '/print/')
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', attrs={"type": "application/ld+json"})
    if not el:
        logger.warning('unable to find ld+json in ' + url)
        return None

    ld_json = json.loads(el.string.replace('\n', '').replace('\r', ''))
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = ld_json['mainEntityOfPage']['@id']
    item['url'] = ld_json['url']

    if ld_json.get('headline'):
        item['title'] = ld_json['headline']
    else:
        item['title'] = ld_json['name']

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {"name": ld_json['author']['name']}

    item['tags'] = []
    el = page_soup.select('ul:has(> li:-soup-contains("Posted in"))')
    if el:
        for it in el[0].find_all('li'):
            if it.a:
                item['tags'].append(it.a.get_text().strip())

    if ld_json.get('itemReviewed') and ld_json['itemReviewed'].get('image'):
        item['_image'] = ld_json['itemReviewed']['image']['url']
    elif ld_json.get('image'):
        item['_image'] = ld_json['image']['url']
    else:
        el = page_soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    item['content_html'] = ''
    if item.get('_image'):
        item['_image'] = re.sub(r'_\d+x\d+\.(jpe?g|png)', r'.\1', item['_image'])
        item['content_html'] += utils.add_image(item['_image'])

    content = page_soup.find(class_='articleContent')
    article_links = page_soup.find(class_='article_links_top')
    if article_links:
        for i, el in enumerate(article_links.find_all('option')):
            if i > 0:
                page_html = utils.get_url_html('https://www.anandtech.com' + el['value'])
                link_soup = BeautifulSoup(page_html, 'lxml')
                it = link_soup.find(class_='articleContent')
                content.append(copy.deepcopy(it))

    if content:
        for el in content.find_all('articleContent'):
            el.unwrap()

        for el in content.select('p img'):
            it = el.find_parent('a')
            if it:
                img_src = it['href']
                link = it['href']
            else:
                img_src = el['src']
                link = ''
            new_html = utils.add_image(img_src, link=link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            it = el.find_parent('p')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)

        for el in content.find_all('table'):
            # Restyle the table
            if el.get('border'):
                del el['border']
            it = el.find('tbody', attrs={"border": True})
            if it:
                del it['border']
            el['width'] = '100%'
            for tr in el.find_all('tr'):
                if tr.get('class') and 'tgrey' in tr['class']:
                    style = 'background-color:#848484; color:white;'
                elif tr.get('class') and 'tlgrey' in tr['class']:
                    style = 'background-color:#ddd; font-weight:bold;;'
                elif tr.get('class') and 'tlblue' in tr['class']:
                    style = 'background-color:#2295A9; color:white;'
                else:
                    style = ''
                if style:
                    if tr.get('style'):
                        tr['style'] += ' ' + style
                    else:
                        tr['style'] = style
                for td in tr.find_all('td'):
                    if td.get('class') and 'tgrey' in td['class']:
                        style = 'background-color:#848484; color:white; padding:8px;'
                    elif td.get('class') and 'tlgrey' in td['class']:
                        style = 'background-color:#ddd; font-weight:bold; padding:8px;'
                    elif td.get('class') and 'tlblue' in td['class']:
                        style = 'background-color:#2295A9; color:white; padding:8px;'
                    elif not tr.get('style') or 'background-color' not in tr['style']:
                        style = 'background-color:#eee; padding:8px;'
                    else:
                        style = 'padding:8px;'
                    if td.get('style'):
                        td['style'] += ' ' + style
                    else:
                        td['style'] = style

            if el.select('td > select'):
                it = el.find_previous_sibling()
                if it and it.name == 'script':
                    arrays = {}
                    mall = re.findall(r'var ([^\s]+) = new Array\(\'(.*?)\'\);', it.string)
                    if mall:
                        for m in mall:
                            arrays[m[0]] = m[1].split("','")

        # arrays = {}
            # for tr in el.find('tr'):
            #     for i, td in enumerate(el.find('tr').find_all('td')):
            #         it = td.find('select')
            #         if it:
            #             arrays['options'] = []
            #             for opt in it.find('option'):
            #                 arrays['options'].append(opt.get_value())
            #             sib = el.find_previous_sibling()
            #             if sib and sib.name == 'script':
            #                 mall = re.findall(r'var ([^\s]+) = new Array\(\'(.*?)\'\);', sib.string)
            #                 if mall:
            #                     for m in mall:
            #                         arrays[m[0]] = m[1].split("','")
            #         if arrays:



        for el in content.select('div.thumbTagContainer:has(> div#gallery)'):
            link = el.a['href']
            if link.startswith('/'):
                link = 'https://www.anandtech.com' + link
            new_html = '<h2>Gallery: <a href="{}">{}</a>'.format(link, el.a.get_text().strip())
            for it in el.find_all('li'):
                img_src = it.img['src'].replace('_thumb', '')
                link = it.a['href']
                if link.startswith('/'):
                    link = 'https://www.anandtech.com' + link
                new_html += utils.add_image(img_src, link=link)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        item['content_html'] += content.decode_contents()
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item
