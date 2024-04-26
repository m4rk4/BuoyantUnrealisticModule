import markdown2, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import config, utils
from feedhandlers import semafor

import logging

logger = logging.getLogger(__name__)


def resize_image(img_path, site_json, width=1080):
    return  '{}{}?w={}'.format(site_json['image_url'], img_path, width)


def add_image(image, site_json, width=1080):
    captions = []
    if image['entity'].get('caption'):
        captions.append(re.sub(r'</?p>', '', image['entity']['caption']))
    if image['entity'].get('credit'):
        captions.append(image['entity']['credit'])
    img_src = resize_image(image['entity']['mediaImage']['url'], site_json, width)
    return utils.add_image(img_src, ' | '.join(captions))


def render_content(content, site_json):
    content_html = ''
    if content['entity']['type'] == 'ParagraphContent':
        content_html += content['entity']['content']['value']

    elif content['entity']['type'] == 'ParagraphImageToolkitElement':
        content_html += add_image(content['entity']['image'], site_json)

    elif content['entity']['type'] == 'ParagraphImageGroup':
        for image in content['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphGalleryInlineElement':
        content_html += '<h3>Gallery: {}</h3>'.format(content['entity']['photoGallery']['entity']['title'])
        for image in content['entity']['photoGallery']['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphImmersiveLead':
        if content['entity'].get('immersiveImage'):
            content_html += add_image(content['entity']['immersiveImage'], site_json)
        else:
            logger.warning('unhandled ParagraphImmersiveLead')

    elif content['entity']['type'] == 'ParagraphVideoToolkit':
        if content['entity']['video']['entity'].get('image'):
            poster = resize_image(content['entity']['video']['entity']['image']['entity']['mediaImage']['url'], site_json)
        else:
            poster = ''
        caption = '<a href="https://www.nationalgeographic.co.uk{}"><strong>{}</strong></a>'.format(content['entity']['video']['entity']['url']['path'], content['entity']['video']['entity']['title'])
        if content['entity']['video']['entity'].get('promoSummary'):
            caption += '<br/>{}'.format(re.sub(r'</?p>', '', content['entity']['video']['entity']['promoSummary']['value']))
        video_src = ''
        if content['entity']['video']['entity']['video']['entity'].get('smilUrl'):
            smil = utils.get_url_html(content['entity']['video']['entity']['video']['entity']['smilUrl'])
            soup = BeautifulSoup(smil, 'html.parser')
            video_src = soup.video['src']
            video_type = soup.video['type']
        if video_src:
            content_html += utils.add_video(video_src, video_type, poster, caption)
        else:
            logger.warning('unhandled ParagraphVideoToolkit')

    elif content['entity']['type'] == 'ParagraphPullQuote':
        content_html += utils.add_pullquote(content['entity']['pullQuote'], content['entity']['source'])

    elif content['entity']['type'] == 'ParagraphInlinePromos':
        pass

    else:
        logger.warning('unhandled content type ' + content['entity']['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    # article_json = api_json['result']['pageContext']['node']['data']['content']
    # if save_debug:
    #     utils.write_file(article_json, './debug/debug.json')

    site_metadata = None
    if api_json.get('staticQueryHashes'):
        for it in api_json['staticQueryHashes']:
            sq_url = '{}://{}/page-data/sq/d/{}.json'.format(split_url.scheme, split_url.netloc, it)
            sq_json = utils.get_url_json(sq_url)
            if sq_json:
                if sq_json.get('data') and sq_json['data'].get('site') and sq_json['data']['site'].get('siteMetadata'):
                    site_metadata = sq_json['data']['site']['siteMetadata']
                    break

    item = {}
    if api_json['result']['pageContext'].get('id'):
        item['id'] = api_json['result']['pageContext']['id']
    else:
        item['id'] = api_json['path']

    item['url'] = 'https://{}{}'.format(split_url.netloc, api_json['path'])

    if api_json['result']['data'].get('markdownRemark'):
        md_remark = api_json['result']['data']['markdownRemark']
        item['title'] = md_remark['frontmatter']['title']

        if md_remark['frontmatter'].get('rawDate'):
            dt = datetime.fromisoformat(md_remark['frontmatter']['rawDate'])
        elif md_remark['frontmatter'].get('date'):
            dt = dateutil.parser.parse(md_remark['frontmatter']['date'])
        else:
            dt = None
        if dt:
            if not dt.tzinfo:
                tz_loc = pytz.timezone(config.local_tz)
                dt = tz_loc.localize(dt).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        if md_remark['frontmatter'].get('rawUpdatedAt'):
            dt = datetime.fromisoformat(md_remark['frontmatter']['rawUpdatedAt'])
            item['date_modified'] = dt.isoformat()

        if site_metadata:
            if site_metadata.get('author'):
                item['author'] = {"name": site_metadata['author']}
            elif site_metadata.get('title'):
                item['author'] = {"name": site_metadata['title']}

        if md_remark['frontmatter'].get('image'):
            item['_image'] = md_remark['frontmatter']['image']['childImageSharp']['fluid']['src']
            if item['_image'].startswith('/'):
                item['_image'] = 'https://' + split_url.netloc + item['_image']

        if md_remark['frontmatter'].get('description'):
            item['summary'] = md_remark['frontmatter']['description']
        elif md_remark.get('excerpt'):
            item['summary'] = md_remark['excerpt']

        if md_remark.get('html'):
            soup = BeautifulSoup(md_remark['html'], 'html.parser')
            for el in soup.find_all(class_='gatsby-resp-image-wrapper'):
                it = el.find('a', class_='gatsby-resp-image-link')
                if it:
                    img_src = it['href']
                else:
                    it = el.find('img')
                    if it:
                        if it.get('srcset'):
                            img_src = utils.image_from_srcset(it['srcset'], 1200)
                        else:
                            img_src = it['src']
                if img_src.startswith('/'):
                    img_src = 'https://' + split_url.netloc + img_src
                # TODO: captions
                new_el = BeautifulSoup(utils.add_image(img_src), 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)

            for el in soup.find_all('iframe'):
                new_el = BeautifulSoup(utils.add_embed(el['src']), 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)

            for el in soup.find_all('a', class_='anchor'):
                it = el.find('svg')
                if it:
                    it.decompose()
                el.unwrap()

            item['content_html'] = str(soup)

        # if article_json.get('subHeadline'):
        #     item['summary'] = article_json['subHeadline']
        #     item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subHeadline'])
        #
        # if article_json.get('immersiveLead'):
        #     item['content_html'] += render_content(article_json['immersiveLead'], site_json)
        # elif article_json.get('image'):
        #     item['content_html'] += add_image(article_json['image'], site_json)
        #
        # if article_json.get('mainContent'):
        #     for content in article_json['mainContent']:
        #         item['content_html'] += render_content(content, site_json)
        #
        # if article_json.get('images'):
        #     for content in article_json['images']:
        #         item['content_html'] += add_image(content, site_json)

    elif api_json['result']['data'].get('wpPost'):
        # https://www.gatsbyjs.com/blog/
        wp_post = api_json['result']['data']['wpPost']
        item['title'] = wp_post['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(wp_post['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if wp_post.get('author') and wp_post['author'].get('node'):
            item['author'] = {"name": wp_post['author']['node']['name']}

        if wp_post.get('tags') and wp_post['tags'].get('nodes'):
            item['tags'] = []
            for it in wp_post['tags']['nodes']:
                item['tags'].append(it['name'])

        if wp_post.get('rawExcerpt') and wp_post['rawExcerpt'].get('text'):
            item['summary'] = wp_post['rawExcerpt']['text']

        if wp_post.get('flexibleContent') and wp_post['flexibleContent'].get('blocks'):
            item['content_html'] = ''
            for block in wp_post['flexibleContent']['blocks']:
                if block['__typename'] == 'WpPost_Flexiblecontent_Blocks_RichText':
                    item['content_html'] += block['richText']
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Image':
                    if block['image']['gatsbyImage']['images']['fallback'].get('srcSet'):
                        img_src = utils.image_from_srcset(block['image']['gatsbyImage']['images']['fallback']['srcSet'], 1200)
                    else:
                        img_src = block['image']['gatsbyImage']['images']['fallback']['src']
                    if img_src.startswith('/'):
                        img_src = 'https://' + split_url.netloc + img_src
                    # TODO: captions
                    item['content_html'] += utils.add_image(img_src)
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Embed':
                    item['content_html'] += utils.add_embed(block['embedUrl'])
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_CodeBlock':
                    if block.get('filename'):
                        item['content_html'] += '<div style="font-weight:bold; background-color:#aaa;">&nbsp;' + block['filename'] + '</div>'
                    item['content_html'] += '<pre style="margin-top:0; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;"><code>' + block['code'].replace('<', '&lt;').replace('>', '&gt;') + '</code></pre>'
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Pullquote':
                    item['content_html'] += utils.add_pullquote(block['pullquoteText'], block.get('citation'))
                else:
                    logger.warning('unhandled flexibleContent block type {} in {}'.format(block['__typename'], item['url']))

    elif api_json['result']['data'].get('story'):
        # https://www.rockefellercenter.com/magazine/
        story_data = api_json['result']['data']['story']
        item['title'] = story_data['titleAndSlug']['title']

        dt = datetime.fromisoformat(story_data['publishAt'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if story_data.get('authors'):
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(story_data['authors']))

        if story_data.get('poster'):
            item['_image'] = story_data['poster']['asset']['fluid']['src']

        if story_data.get('excerpt'):
            item['summary'] = story_data['excerpt']

        if story_data.get('_rawBody'):
            item['content_html'] = ''
            for block in story_data['_rawBody']:
                item['content_html'] += semafor.render_block(block)
            item['content_html'] = item['content_html'].replace('https://img.semafor.com', site_json['image_path'])

    elif api_json['result']['data'].get('post'):
        # https://thefactbase.com/
        post_json = api_json['result']['data']['post']
        item['title'] = post_json['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(post_json['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if post_json.get('author'):
            item['author'] = {"name": post_json['author']['name']}

        item['tags'] = []
        if post_json.get('keywords'):
            item['tags'] += post_json['keywords'].copy()
        if post_json.get('tags'):
            for it in post_json['tags']:
                item['tags'].append(it['name'])

        if post_json.get('excerpt'):
            item['summary'] = post_json['excerpt']

        if post_json.get('thumbnail'):
            if post_json['thumbnail'].get('ImageSharp_hero'):
                item['_image'] = 'https://' + split_url.netloc + post_json['thumbnail']['ImageSharp_hero']['images']['fallback']['src']
            elif post_json['thumbnail'].get('ImageSharp_vertical'):
                item['_image'] = 'https://' + split_url.netloc + post_json['thumbnail']['ImageSharp_vertical']['images']['fallback']['src']

        item['content_html'] = ''
        if item.get('_image'):
            item['content_html'] += utils.add_image(item['_image'])

        def render_mdx(mdx_str):
            n = len(mdx_str)
            m = re.search(r'^"([^"]+)"', mdx_str, flags=re.S)
            if not m:
                logger.warning('unknown mdx tag in ' + mdx_str)
                return
            tag = m.group(1)
            end_tag = ''
            mdx_html = ''
            i = mdx_str.find(',') + 2
            if mdx_str[i] == '{':
                params = re.search(r'\{(.*?)\}(?=,|$)', mdx_str[i:], flags=re.S)
            else:
                params = re.search(r'([^,]+)', mdx_str[i:], flags=re.S)
            if tag == 'a':
                m = re.search(r'"href": "([^"]+)"', params.group(1), flags=re.S)
                if m:
                    mdx_html = '<a href="{}">'.format(m.group(1))
                    end_tag = '</a>'
                else:
                    logger.warning('unknown link href in ' + mdx_str)
            elif tag == 'img':
                m = re.search(r'"src": "([^"]+)"', params.group(1), flags=re.S)
                if m:
                    # TODO: captions
                    mdx_html = utils.add_image(m.group(1))
                else:
                    logger.warning('unknown img src in ' + mdx_str)
            else:
                mdx_html = '<{}>'.format(tag)
                end_tag = '</{}>'.format(tag)
            i += len(params.group(0))
            while i < n and mdx_str[i] == ',':
                i += 2
                # print('value: ' + mdx_str[i:])
                if mdx_str[i] == '"':
                    val = re.search(r'"(.*?)"(?=,|\)|$)', mdx_str[i:], flags=re.S)
                    if val:
                        mdx_html += val.group(1).replace('\\u2019', '&#x2019')
                elif mdx_str[i:i+3] == 'mdx':
                    val = re.search(r'mdx\((.*)\)(?=,|\)|$)', mdx_str, flags=re.S)
                    if val:
                        mdx_html += render_mdx(val.group(1))
                if val:
                    i += len(val.group(0))
                else:
                    logger.warning('unknown value in ' + mdx_str[i:])
                    break
            mdx_html += end_tag
            return mdx_html

        for mdx in re.findall(r'mdx\((\".*?)\)(?=, mdx\(\"|\);\n}\n;)', post_json['body'], flags=re.S):
            item['content_html'] += render_mdx(mdx)

    elif api_json['result']['data'].get('essay'):
        # https://publicdomainreview.org/essays/
        essay_data = api_json['result']['data']['essay']['data']
        item['title'] = essay_data['Title']

        dt = datetime.fromisoformat(essay_data['Published_Date'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if essay_data.get('Contributors'):
            authors = []
            for it in essay_data['Contributors']:
                authors.append(it['data']['Name'])
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        item['tags'] = []
        if essay_data.get('Categories'):
            item['tags'] += essay_data['Categories'].copy()
        if essay_data.get('Tags'):
            for it in essay_data['Tags']:
                item['tags'].append(it['data']['Label'])
        if not item.get('tags'):
            del item['tags']

        if essay_data.get('Featured_Image_Path'):
            item['_image'] = site_json['image_path'] + essay_data['Featured_Image_Path']

        item['content_html'] = ''
        if essay_data.get('Intro'):
            item['summary'] = essay_data['Intro']
            item['content_html'] += markdown2.markdown(essay_data['Intro'])

        body = markdown2.markdown(essay_data['Body'])
        def sub_image(matchobj):
            nonlocal site_json
            m = re.search(r'path=\{([^\}]+)\}', matchobj.group(0))
            if m:
                if m.group(1).startswith('/'):
                    img_src = site_json['image_path'] + m.group(1)
                else:
                    img_src = m.group(1)
            m = re.search(r'caption=\{([^\}]+)\}', matchobj.group(0))
            if m:
                caption = m.group(1)
            else:
                caption = ''
            return utils.add_image(img_src, caption)
        body = re.sub(r'<p>\{image.*?endimage\}</p>', sub_image, body, flags=re.S)

        soup = BeautifulSoup(body, 'html.parser')
        for el in soup.find_all('blockquote'):
            el.attrs = {}
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
        item['content_html'] += str(soup)

        if essay_data.get('Footnotes'):
            item['content_html'] = re.sub(r'\[\^(\d+)\]', r'<sup>\1</sup>', item['content_html'])
            item['content_html'] += '<div>&nbsp;</div><hr/><h3>Notes:</h3>'
            item['content_html'] += '<ol>' + re.sub(r'\[\^\d+\]:(.*?)(\n|$)', r'<li>\1</li>', essay_data['Footnotes']) + '</ol>'

    if api_json['result']['pageContext'].get('category'):
        if not item.get('tags'):
            item['tags'] = []
        if api_json['result']['pageContext']['category'] not in item['tags']:
            item['tags'].append(api_json['result']['pageContext']['category'])

    if item.get('content_html'):
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    if len(split_url.path) <= 1:
        path = '/index'
    elif site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    page_json = api_json['result']['pageContext']['node']['data']['content']
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    articles = []
    for content in page_json['mainContent']:
        if content['entity']['type'] == 'ParagraphContentPackage1':
            articles.append(content['entity']['cardGlobalLarge']['entity']['url']['path'])
        else:
            logger.warning('unhandled feed content type ' + content['entity']['type'])

    for content in page_json['termContent']['data']['featured']:
        articles.append(content['props']['data']['url'])

    for content in page_json['termContent']['data']['pagination']:
        for it in content:
            articles.append(it[1])

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['title']
    feed_items = []
    for path in articles:
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, path)
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed

