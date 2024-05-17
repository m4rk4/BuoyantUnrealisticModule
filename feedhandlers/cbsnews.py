import json, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def add_figure(figure):
    # print(figure)
    new_html = ''
    if 'embed--type-image' in figure['class']:
        it = figure.find('img')
        if it:
            if it.get('data-srcset'):
                img_src = utils.image_from_srcset(it['data-srcset'], 1200)
            elif it.get('srcset') and not it['srcset'].startswith('data:'):
                img_src = utils.image_from_srcset(it['srcset'], 1200)
            elif it.get('data-src'):
                img_src = it['data-src']
            else:
                img_src = it['src']
            it = figure.find('a', class_='content__link')
            if it:
                link = it['href']
            else:
                link = ''
            captions = []
            if figure.figcaption:
                it = figure.find(class_='embed__caption')
                if it and it.get_text().strip():
                    captions.append(it.decode_contents())
                it = figure.find(class_='embed__credit')
                if it and it.get_text().strip():
                    captions.append(it.decode_contents())
            new_html = utils.add_image(img_src, ' | '.join(captions), link=link)
    elif 'embed--type-youtube-video' in figure['class']:
        it = figure.find('iframe')
        if it:
            if it.get('data-src'):
                new_html = utils.add_embed(it['data-src'])
            elif it.get('src'):
                new_html = utils.add_embed(it['src'])
    elif 'embed--type-video' in figure['class']:
        it = figure.find('a', class_='embed__headline-link')
        if it and 'cbsnews.com' in it['href']:
            embed_item = get_content(it['href'], {"embed": True}, {}, False)
            if embed_item:
                new_html = embed_item['content_html']
    if new_html:
        new_el = BeautifulSoup(new_html, 'html.parser')
        figure.replace_with(new_el)
        return new_html
    else:
        logger.warning('unhandled figure class ' + str(figure['class']))
        return str(figure)

def format_content(content):
    for el in content.find_all(['aside', 'script', 'style']):
        el.decompose()
    for el in content.find_all(class_=['ad-wrapper', 'content-author', 'content__tags']):
        el.decompose()
    for el in content.find_all(text=lambda text: isinstance(text, Comment)):
        el.extract()
    for el in content.find_all('figure'):
        add_figure(el)
    for el in content.find_all(attrs={"data-shortcode": True}):
        if el['data-shortcode'] == 'image':
            captions = []
            if el.get('data-image-caption'):
                captions.append(re.sub(r'</?p>', '', el['data-image-caption']))
            if el.get('data-image-credit'):
                captions.append(el['data-image-credit'])
            # TODO: resize image - date/uuid/thumbnail/widthxheight/md5hash?/filename
            img_src = 'https://assets3.cbsnewsstatic.com/hub/i/r/{}/{}/{}'.format(el['data-image-date-created'], el['data-uuid'], el['data-image-filename'])
            new_html = utils.add_image(img_src, ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled data-shortcode ' + el['data-shortcode'])


def get_content(url, args, site_json, save_debug=False):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    article_json = {}
    video_json = {}
    live_blog = {}
    image_gallery = {}
    all_ld_json = []
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        all_ld_json.append(ld_json)
        if ld_json['@type'] == 'NewsArticle':
            article_json = ld_json
        elif ld_json['@type'] == 'VideoObject':
            video_json = ld_json
        elif ld_json['@type'] == 'LiveBlogPosting':
            live_blog = ld_json
        elif ld_json['@type'] == 'ImageGallery':
            image_gallery = ld_json
    if not article_json:
        logger.warning('unable to find ld+json NewsArticle in ' + url)
        return None
    if save_debug:
        utils.write_file(all_ld_json, './debug/debug.json')
        utils.write_file(page_html, './debug/debug.html')

    item = {}
    item['id'] = article_json['mainEntityOfPage']['@id']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('dateModified'):
        dt = datetime.fromisoformat(article_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    if article_json.get('author'):
        if isinstance(article_json['author'], dict):
            item['author'] = {"name": article_json['author']['name']}
        elif isinstance(article_json['author'], list):
            authors = []
            for it in article_json['author']:
                authors.append(it['name'])
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('publisher'):
        item['author'] = {"name": article_json['publisher']['name']}

    item['tags'] = []
    if article_json.get('articleSection'):
        item['tags'] += article_json['articleSection'].copy()
    if article_json.get('keywords'):
        item['tags'] += article_json['keywords'].copy()
    if len(item['tags']) == 0:
        del item['tags']

    if article_json.get('image'):
        item['_image'] = article_json['image']['url']
    if article_json.get('thumbnailUrl'):
        item['_image'] = article_json['thumbnailUrl']

    if article_json.get('description'):
        item['summary'] = article_json['description']

    if video_json:
        item['_video'] = video_json['contentUrl']
        item['content_html'] = utils.add_video(item['_video'], 'application/x-mpegURL', video_json['thumbnailUrl'], '<a href="{}">{}</a>'.format(item['url'], video_json['name']))
        if video_json.get('description') and 'embed' not in args:
            item['content_html'] += '<p>' + video_json['description'] + '</p>'
    else:
        if 'embed' in args:
            item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
            if item.get('_image'):
                item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
            item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
            if item.get('summary'):
                item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
            item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
            return item

        item['content_html'] = ''
        if '/pictures/' in item['url']:
            if soup.find('article', class_='content-image-gallery'):
                for media in soup.select('article.content-image-gallery > section.content__body'):
                    it = media.find(class_='content__section-headline')
                    if it:
                        it.name = 'h3'
                        it.attrs = {}
                    it = media.find('figure')
                    if it:
                        add_figure(it)
                    item['content_html'] += media.decode_contents()
                return item
            elif image_gallery:
                # Does not include image captions and credits
                for media in image_gallery['associatedMedia']:
                    item['content_html'] += '<h3>' + media['name'] + '</h3>'
                    if media['@type'] == 'ImageObject':
                        item['content_html'] += utils.add_image(media['thumbnailUrl'])
                    elif media['@type'] == 'VideoObject':
                        item['content_html'] += utils.add_video(media['contentUrl'], 'application/x-mpegURL', media['thumbnailUrl'], '<a href="{}">{}</a>'.format(media['embedUrl'], media['name']))
                    else:
                        logger.warning('unhandled gallery media type {} in {}'.format(media['@type'], item['url']))
                    if media.get('description'):
                        item['content_html'] += '<p>' + media['description'] + '</p>'
                return item

        if '/live-updates/' in item['url']:
            content_body = soup.find('section', class_='content__post--intro')
        else:
            content_body = soup.find('section', class_='content__body')

        if content_body:
            # Add hero media if it's not the first element
            if content_body.find(True, recursive=False).name != 'figure':
                if article_json.get('video'):
                    item['content_html'] += utils.add_video(article_json['video']['contentUrl'], 'application/x-mpegURL', article_json['video']['thumbnailUrl'], '<a href="{}">{}</a>'.format(article_json['video']['embedUrl'], article_json['video']['name']))
                else:
                    el = soup.select('article.content > figure.is-hero')
                    if el:
                        item['content_html'] += add_figure(el[0])
            format_content(content_body)
            item['content_html'] += content_body.decode_contents()

        if '/live-updates/' in item['url']:
            if live_blog and live_blog.get('liveBlogUpdate'):
                for update in live_blog['liveBlogUpdate']:
                    item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
                    if update.get('headline'):
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + update['headline'] + '</div>'
                    if update.get('author'):
                        authors = []
                        if isinstance(update['author'], dict):
                            item['author'].append(update['author']['name'])
                        elif isinstance(update['author'], list):
                            for it in article_json['author']:
                                authors.append(it['name'])
                        item['content_html'] += '<div>By ' + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)) + '</div>'
                    if update.get('datePublished'):
                        dt = datetime.fromisoformat(update['datePublished'])
                        item['content_html'] += '<div>' +  utils.format_display_date(dt) + '</div>'
                    if update.get('articleBody'):
                        it = BeautifulSoup(update['articleBody'], 'html.parser')
                        format_content(it)
                        if it.find(True, recursive=False).name == 'figure':
                            item['content_html'] += '<div>&nbsp;</div>'
                        item['content_html'] += str(it)
            else:
                for update in soup.select('div.content__post-items > section.post-update'):
                    if 'content__post--intro' in update['class']:
                        continue
                    item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
                    it = update.find(class_='post-update__headline')
                    if it:
                        item['content_html'] += '<div style="font-size:1.1em; font-weight:bold;">' + it.get_text() + '</div>'
                    it = update.find(class_='post-update__author')
                    if it:
                        item['content_html'] += '<div>' + it.get_text() + '</div>'
                    it = update.find('time', class_='post-update__time-ago')
                    if it:
                        dt = datetime.fromisoformat(it['datetime'])
                        item['content_html'] += '<div>' +  utils.format_display_date(dt) + '</div>'
                    it = update.find(class_='post-update__bodytext')
                    if it:
                        format_content(it)
                        if it.find(True, recursive=False).name == 'figure':
                            item['content_html'] += '<div>&nbsp;</div>'
                        item['content_html'] += it.decode_contents()

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
