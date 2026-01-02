import pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url, use_proxy=True, use_curl_cffi=True)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    item = {}
    soup = BeautifulSoup(page_html, 'html.parser')
    article = soup.find('article')
    if article:
        item['id'] = article['data-article-id']
        item['url'] = article['data-url']
        item['title'] = article['data-title']

        el = soup.find('meta', attrs={"itemprop": "datePublished"})
        if el:
            tz_loc = None
            it = soup.find(class_='article__published')
            if it:
                date = it.get_text()
                if 'EST' in date:
                    tz_loc = pytz.timezone('US/Eastern')
                elif 'CST' in date:
                    tz_loc = pytz.timezone('US/Central')
                elif 'MST' in date:
                    tz_loc = pytz.timezone('US/Mountain')
                elif 'PST' in date:
                    tz_loc = pytz.timezone('US/Pacific')
            if not tz_loc:
                if site_json.get('timezone'):
                    tz_loc = pytz.timezone(site_json['timezone'])
                else:
                    tz_loc = pytz.timezone(config.local_tz)
            dt_loc = dateutil.parser.parse(el['content'])
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        el = soup.find('meta', attrs={"itemprop": "dateModified"})
        if el:
            if re.search(r'EST|EDT', el['content']):
                dt_loc = datetime.strptime(el['content'].replace('EST', 'EDT'), '%I:%M %p EDT %B %d, %Y')
                tz_loc = pytz.timezone('US/Eastern')
            elif re.search(r'CST|CDT', el['content']):
                dt_loc = datetime.strptime(el['content'].replace('CST', 'CDT'), '%I:%M %p CDT %B %d, %Y')
                tz_loc = pytz.timezone('US/Central')
            elif re.search(r'MST|MDT', el['content']):
                dt_loc = datetime.strptime(el['content'].replace('MST', 'MDT'), '%I:%M %p MDT %B %d, %Y')
                tz_loc = pytz.timezone('US/Mountain')
            elif re.search(r'PST|PDT', el['content']):
                dt_loc = datetime.strptime(el['content'].replace('PST', 'PDT'), '%I:%M %p PDT %B %d, %Y')
                tz_loc = pytz.timezone('US/Mountain')
            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
            item['date_modified'] = dt.isoformat()

        # item['author'] = {"name": article['data-author']}
        authors = [it.strip() for it in article['data-author'].split(',')]
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        item['tags'] = article['data-keywords'].split(',')
        item['tags'] += article['data-watson-keywords'].split(',')

        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']

        item['content_html'] = ''
        if article.get('data-abstract'):
            item['summary'] = article['data-abstract']
            item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

        el = soup.find(class_='article__lead-asset')
        if el:
            if el.find(class_='photo'):
                captions = []
                it = el.find(class_='photo__caption')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                it = el.find(class_='photo__credit')
                if it and it.get_text().strip():
                    captions.append(it.get_text().strip())
                img_src = ''
                img = el.find(class_='lazy-image__image')
                if img:
                    item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
                else:
                    img = el.find(class_='photo__main')
                    if img:
                        img_src = utils.image_from_srcset(img['srcset'], 1000)
                if img_src:
                    item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
                else:
                    logger.warning('unhandled lead asset photo in ' + item['url'])
            else:
                it = el.find(class_='video')
                if it:
                    item['content_html'] += utils.add_video(it['data-stream'], 'application/x-mpegURL', it['data-thumbnail'], it['data-title'])
                else:
                    logger.warning('unhandled lead asset in ' + item['url'])

        article_body = article.find(class_='article__body')
        if article_body:
            for el in article_body.find_all('a'):
                if el['href'].startswith('//'):
                    el['href'] = 'https:' + el['href']
                elif el['href'].startswith('/'):
                    el['href'] = 'https://' + urlsplit(item['url']).netloc + el['href']

            for el in article_body.children:
                if el.name == 'div':
                    if el.get('style') == 'display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;':
                        continue

                    if not el.get('class'):
                        el.decompose()

                    elif 'article__section_type_text' in el['class']:
                        if el.find(class_=re.compile(r'cms__embed-related-story')):
                            el.decompose()
                        elif re.search(r'<(h3|strong)[^>]*>(MORE HEADLINES|More from \w+|RELATED|SUBSCRIBE):', el.decode_contents()):
                            el.decompose()
                        else:
                            el.unwrap()

                    elif 'article__section_type_photo' in el['class']:
                        captions = []
                        it = el.find(class_='photo__caption')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        it = el.find(class_='photo__credit')
                        if it and it.get_text().strip():
                            captions.append(it.get_text().strip())
                        img_src = ''
                        img = el.find(class_=['lazy-image__image', 'photo__main'])
                        if img:
                            if img.get('data-srcset'):
                                img_src = utils.image_from_srcset(img['data-srcset'], 1000)
                            elif img.get('srcset'):
                                img_src = utils.image_from_srcset(img['srcset'], 1000)
                        if img_src:
                            new_html = utils.add_image(img_src, ' | '.join(captions))
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            el.insert_after(new_el)
                            el.decompose()
                        else:
                            logger.warning('unhandled photo in ' + item['url'])

                    elif 'article__section_type_gallery' in el['class']:
                        it = el.find(class_='gallery')
                        new_html = '<h3>' + it['data-title'] + '</h3>'
                        new_html += '<div style="display:flex; flex-wrap:wrap; gap:8px; margin:1em 0;">'
                        for it in el.find_all(class_='gallery__slide'):
                            captions = []
                            if it.get('data-caption'):
                                captions.append(it['data-caption'])
                            if it.get('data-credit'):
                                captions.append(it['data-credit'])
                            img_src = ''
                            img = it.find(class_=['lazy-image__image'])
                            if img:
                                img_src = utils.image_from_srcset(img['data-srcset'], 1920)
                                thumb = utils.image_from_srcset(img['data-srcset'], 750)
                            else:
                                img = it.find('img', class_='gallery__image')
                                if img:
                                    img_src = utils.image_from_srcset(img['srcset'], 1920)
                                    thumb = utils.image_from_srcset(img['srcset'], 750)
                            if img_src:
                                new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, ' | '.join(captions), link=img_src, fig_style="margin:0; padding:0;") + '</div>'
                            else:
                                logger.warning('unhandled gallery slide image in ' + item['url'])
                        new_html += '</div>'
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.replace_with(new_el)

                    elif 'article__section_type_embed' in el['class']:
                        new_html = ''
                        it = el.find('iframe')
                        if it:
                            if 'count.gif' in it['src']:
                                el.decompose()
                            else:
                                new_html = utils.add_embed(it['src'])
                        elif el.find(id='fb-root'):
                            it = el.find('blockquote')
                            new_html = utils.add_embed(it['cite'])
                        else:
                            it = el.find('blockquote')
                            if it.get('class'):
                                if 'twitter-tweet' in it['class']:
                                    links = it.find_all('a')
                                    new_html = utils.add_embed(links[-1]['href'])
                                elif 'instagram-media' in it['class']:
                                    new_html = utils.add_embed(it['data-instgrm-permalink'])
                        if new_html:
                            new_el = BeautifulSoup(new_html, 'html.parser')
                            el.insert_after(new_el)
                            el.decompose()
                        else:
                            logger.warning('unhandled article section embed in ' + item['url'])

                    elif 'article__section_type_video' in el['class']:
                        it = el.find(class_='video__endslate-heading')
                        if it and 'more videos' in it.get_text().lower():
                            el.decompose()

                    elif 'article__section_type_ad' in el['class'] or 'related-stories' in el['class']:
                            el.decompose()

                    else:
                        logger.warning('unhandled article section {} in {}'.format(el['class'], item['url']))

        # for el in article_body.select('p > strong:-soup-contains("SUBSCRIBE")'):
        #     it = el.find_parent('p')
        #     it.decompose()

        item['content_html'] += article_body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.wkyc.com/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
