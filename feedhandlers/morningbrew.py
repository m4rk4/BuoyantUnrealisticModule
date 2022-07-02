import re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_json(url):
    tld = tldextract.extract(url)
    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    if path:
        path += '.json'
    else:
        path = '/index.json'

    sites_json = utils.read_json_file('./sites.json')
    build_id = sites_json[tld.domain]['buildId']
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, build_id, path)
    next_json = utils.get_url_json(next_url, retries=1)
    if not next_json:
        logger.debug('updating morningbrew.com buildId')
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m:
            sites_json[tld.domain]['buildId'] = m.group(1)
            utils.write_file(sites_json, './sites.json')
            next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, m.group(1), path)
            next_json = utils.get_url_json(next_url)
            if not next_json:
                return None
    return next_json


def format_content(content):
    content_html = ''
    end_tag = ''
    if content.get('listItem'):
        if content['listItem'] == 'bullet':
            content_html += '<ul><li>'
            end_tag += '</li></ul>'
        elif content['listItem'] == 'number':
            content_html += '<ol><li>'
            end_tag += '</li></ol>'
        else:
            logger.debug('unknown listItem type ' + content['listItem'])
            content_html += '<ul><li>'
            end_tag += '</li></ul>'
    elif content.get('style'):
        if content['style'] == 'normal':
            content_html += '<p>'
            end_tag += '</p>'
        elif re.search(r'h\d', content['style']):
            content_html += '<{}>'.format(content['style'])
            end_tag += '</{}>'.format(content['style'])
        else:
            logger.warning('unhandled block style ' + content['style'])

    if content['_type'] == 'block':
        for child in content['children']:
            if child['_type'] == 'span':
                end_marks = ''
                if child.get('marks'):
                    for mark in child['marks']:
                        markdef = next((it for it in content['markDefs'] if it['_key'] == mark), None)
                        if markdef:
                            if markdef['_type'] == 'link':
                                content_html += '<a href="{}">'.format(markdef['href'], child['text'])
                                end_marks += '</a>'
                            else:
                                logger.warning('unhandled markdef type ' + markdef['_type'])
                        else:
                            content_html += '<{}>'.format(mark)
                            end_marks = '</{}>'.format(mark) + end_marks
                content_html += child['text'] + end_marks
            else:
                logger.warning('unhandled child type ' + child['_type'])

    elif content['_type'] == 'imageWithAlt':
        m = re.search('image-(.*)-(.*)$', content['asset']['_ref'])
        if m:
            img_src = 'https://cdn.sanity.io/images/bl383u0v/production/{}.{}?q=70&auto=format'.format(m.group(1), m.group(2))
            caption = ''
            if content.get('source'):
                for source in content['source']:
                    caption += format_content(source)
                caption = re.sub(r'^<p>(.*)</p>$', r'\1', caption)
            content_html += utils.add_image(img_src, caption)
        else:
            logger.warning('unhandled imageWithAlt')

    elif content['_type'] == 'iframe':
        soup = BeautifulSoup(content['embed'], 'html.parser')
        content_html += utils.add_embed(soup.iframe['src'])

    elif content['_type'] == 'customizableButton':
        content_html += '<p><a href="{}"><strong>{}</strong></a></p>'.format(content['url'], content['cta'])

    else:
        logger.warning('unknown content type ' + content['_type'])

    return content_html + end_tag


def get_content(url, args, save_debug=False):
    next_json = get_next_json(url)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    apollo_state = next_json['pageProps']['initialApolloState']

    item = {}
    for key, val in apollo_state['ROOT_QUERY'].items():
        if key.startswith('v2Story'):
            if not val:
                return None
            item['id'] = val['slug']
            item['url'] = 'https://www.morningbrew.com/{}/stories/{}'.format(val['vertical']['slug'], val['slug'])
            item['title'] = val['title']
        
            dt = datetime.fromisoformat(val['publishDate'].replace('Z', '+00:00'))
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        
            if val.get('authors'):
                authors = []
                for author in val['authors']:
                    authors.append(author['name'])
                if authors:
                    item['author'] = {}
                    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

            if val.get('tags'):
                item['tags'] = []
                for it in val['tags']:
                    tag = apollo_state[it['__ref']]
                    item['tags'].append(tag['name'])

            item['content_html'] = ''

            if val.get('subtitle'):
                item['content_html'] += '<p><em>{}</em></p>'.format(val['subtitle'])

            if val.get('headerImage'):
                ref = val['headerImage']['asset']['__ref']
                item['_image'] = apollo_state[ref]['url']
                caption = ''
                if val['headerImage'].get('source'):
                    for it in val['headerImage']['source']:
                        caption += format_content(it)
                    caption = re.sub(r'^<p>(.*)</p>$', r'\1', caption)
                item['content_html'] += utils.add_image(item['_image'], caption)
        
            if val.get('og'):
                item['summary'] = val['og']['description']

            if val.get('content'):
                for content in val['content']:
                    item['content_html'] += format_content(content)

            item['content_html'] = re.sub(r'</[ou]l><[ou]l>', '', item['content_html'])

            break

        elif key.startswith('v2Issue'):
            item['id'] = url
            item['url'] = url
            item['title'] = '{}: {}'.format(val['title'], val['subjectLine'])

            if val['date'].endswith('Z'):
                dt = datetime.fromisoformat(val['date'].replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(val['date']).astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            item['author'] = {"name": val['vertical']['name']}

            ref = val['vertical']['og']['image']['asset']['__ref']
            item['_image'] = apollo_state[ref]['url']

            #if val.get('primaryImage'):
            #    ref = val['primaryImage']['asset']['__ref']
            #    item['_image'] = apollo_state[ref]['url']

            item['content_html'] = utils.add_image(item['_image'])
            content_links = []

            m = re.findall(r'<!-- (ARTICLE|HEADER|MARKETS) ---?>(.*?)<!-- END \1 ---?>', val['html'], flags=re.M|re.S)
            if not m:
                m = re.findall(r'<!-- START ([^-]+)-->(.*?)<!-- END \1-->', val['html'], flags=re.M | re.S)
                if not m:
                    logger.warning('unable to determine issue sections in ' + item['url'])
                    return None

            if 'HEADER' not in m[0][0]:
                soup = BeautifulSoup(val['html'], 'html.parser')
                el = soup.find(class_='topBlurb')
                article = []
                article.append('HEADER')
                article.append(str(el))
                m.insert(0, article)

            for article in m:
                article_html = ''
                article_item = None
                soup = BeautifulSoup(article[1], 'html.parser')

                #logger.debug(article[0])
                if article[0] == 'HEADER':
                    for el in soup.find_all(align='center'):
                        el.decompose()
                elif article[0] == 'HEADER CARD ':
                    el = soup.find('td', class_='mob-wrap')
                    if el:
                        parent = el.find_parent('table')
                        if parent:
                            it = parent.find_previous_sibling()
                            if it:
                                it.decompose()
                            parent.decompose()
                else:
                    article_html += '<hr/>'

                subtitle = ''
                el = soup.find('h3')
                if el:
                    subtitle = el.get_text().strip()
                else:
                    el = soup.find(class_='story-tag')
                    if el:
                        subtitle = el.get_text().strip()
                    else:
                        for el in soup.find_all('span', style=True):
                            if re.search(r'font-size: 18px;', el['style']) and re.search(r'font-weight: 700;', el['style']):
                                subtitle = el.get_text().strip()
                if re.search(r'SHARE THE BREW|share sidekick', subtitle, flags=re.I):
                    continue

                title = soup.find('h1')
                if title:
                    if subtitle:
                        article_html += '<h3 style="margin-bottom:0;">' + subtitle + '</h3>'
                    link = title.find('a')
                    if link and link['href'] != '#':
                        article_url = utils.clean_url(link['href'])
                        if 'brew' not in urlsplit(article_url).netloc:
                            continue
                        if article_url in content_links:
                            continue
                        content_links.append(article_url)
                        article_html += '<h2 style="margin-top:0;"><a href="{}">{}</a></h2>'.format(article_url, title.get_text().strip())
                        article_item = get_content(article_url, {}, False)
                    else:
                        article_html += '<h2 style="margin-top:0;">{}</h2>'.format(title.get_text().strip())
                elif subtitle:
                    article_html += '<h3>' + subtitle + '</h3>'

                if article[0] == 'MARKETS':
                    article_html += '<table style="width:80%; margin-left:auto; margin-right:auto; border:1px solid black; border-collapse:collapse;">'
                    for el in soup.find_all('td', class_='lastline'):
                        article_html += '<tr style="border:1px solid black; border-collapse:collapse;">'
                        for it in el.find_all(class_='markets-table-text'):
                            article_html += '<td style="padding:0.3em;">{}</td>'.format(it.get_text().strip())
                        article_html += '</tr>'
                        el.decompose()
                    article_html += '</table>'

                if article_item:
                    article_html += article_item['content_html']
                else:
                    el = soup.find(class_='sponsored-tag')
                    if el:
                        continue
                    el = soup.find(class_='story-header-image')
                    if el:
                        if 'https://media.sailthru.com/' in el['src']:
                            continue
                        caption = soup.find(class_='source')
                        if caption:
                            article_html += utils.add_image(el['src'], caption.get_text())
                        else:
                            article_html += utils.add_image(el['src'])
                        el.decompose()
                    for el in soup.find_all(['a', 'img', 'p', 'ol', 'ul']):
                        if not el.name:
                            continue
                        if el.get('style'):
                            del el['style']
                        for it in el.find_all(style=True):
                            del it['style']
                        if el.name == 'a':
                            if el.get('class') and 'mystery-box-button' in el['class']:
                                parent = el.find_parent('tr')
                                if parent.get('class') and 'mob-show' in parent['class']:
                                    article_html += '<p><a href="{}">{}</a></p>'.format(el['href'], el.get_text().strip())
                            continue
                        elif el.name == 'img':
                            if 'https://media.sailthru.com/' in el['src']:
                                el.decompose()
                            else:
                                if el.get('width') and int(el['width']) < 100:
                                    continue
                                new_html = utils.add_image(el['src'])
                                parent = el.find_parent('p')
                                if parent:
                                    new_el = BeautifulSoup(new_html, 'html.parser')
                                    el.insert_after(new_el)
                                else:
                                    article_html += new_html
                                el.decompose()
                        if el and el.name:
                            it = el.find('font')
                            if it:
                                it.unwrap()
                            article_html += str(el)
                item['content_html'] += article_html

    return item


def get_author_feed(args, save_debug):
    query = '''fragment ImageWithAltFragment on ImageWithAlt {
  alt
  asset {
    _id
    url
    path
    assetId
    extension
    webpUrl
    metadata {
      lqip
      __typename
    }
    __typename
  }
  hotspot {
    width
    height
    x
    y
    __typename
  }
  crop {
    top
    left
    bottom
    right
    __typename
  }
  __typename
}

fragment StoryCardStoryEditorial on StoryEditorial {
  slug
  title
  _id
  tags {
    name
    __typename
  }
  originalTag
  headerImage {
    ...ImageWithAltFragment
    __typename
  }
  publishDate
  authors {
    name
    __typename
  }
  vertical {
    slug
    __typename
  }
  __typename
}

fragment StoryCardStoryBrandedContent on StoryBrandedContent {
  slug
  title
  _id
  tags {
    name
    __typename
  }
  originalTag
  headerImage {
    ...ImageWithAltFragment
    __typename
  }
  publishDate
  authors {
    name
    __typename
  }
  vertical {
    slug
    __typename
  }
  __typename
}

query GetAuthorStories($username: String!, $filters: AllStoriesByAuthorFilters, $limit: Int, $offset: Int, $query: String) {
  allStoriesByAuthor(
    username: $username
    filters: $filters
    limit: $limit
    offset: $offset
    query: $query
  ) {
    ... on StoryEditorial {
      ...StoryCardStoryEditorial
      __typename
    }
    ... on StoryBrandedContent {
      ...StoryCardStoryBrandedContent
      __typename
    }
    __typename
  }
}
'''
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    post_data = {"operationName": "GetAuthorStories",
                 "query": query,
                 "variables": {
                     "username": paths[1],
                     "filters": {"tagName": ""},
                     "query": "",
                     "offset": 0,
                     "limit": 10}
                 }
    gql_json = utils.post_url('https://singularity.morningbrew.com/graphql', json_data=post_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')
    feed_urls = []
    for article in gql_json['data']['allStoriesByAuthor']:
        url = 'https://www.morningbrew.com/{}/stories/{}'.format(article['vertical']['slug'], article['slug'])
        feed_urls.append(url)
    return feed_urls


def get_tag_feed(args, save_debug):
    query = '''fragment ImageWithAltFragment on ImageWithAlt {
  alt
  asset {
    _id
    url
    path
    assetId
    extension
    webpUrl
    metadata {
      lqip
      __typename
    }
    __typename
  }
  hotspot {
    width
    height
    x
    y
    __typename
  }
  crop {
    top
    left
    bottom
    right
    __typename
  }
  __typename
}

fragment StoryCardStoryBrandedContent on StoryBrandedContent {
  slug
  title
  _id
  tags {
    name
    __typename
  }
  originalTag
  headerImage {
    ...ImageWithAltFragment
    __typename
  }
  publishDate
  authors {
    name
    __typename
  }
  vertical {
    slug
    __typename
  }
  __typename
}

fragment StoryCardStoryEditorial on StoryEditorial {
  slug
  title
  _id
  tags {
    name
    __typename
  }
  originalTag
  headerImage {
    ...ImageWithAltFragment
    __typename
  }
  publishDate
  authors {
    name
    __typename
  }
  vertical {
    slug
    __typename
  }
  __typename
}

query GetSearchStories($limit: Int, $offset: Int, $query: String, $filters: AllStoriesFilters) {
  allStorySearch(limit: $limit, offset: $offset, query: $query, filters: $filters) {
    ...StoryCardStoryBrandedContent
    ...StoryCardStoryEditorial
    __typename
  }
}
'''
    split_url = urlsplit(args['url'])
    url_query = parse_qs(split_url.query)
    if not url_query.get('tag'):
        return None
    tag = url_query['tag'][0]

    post_data = {"operationName": "GetSearchStories",
                 "query": query,
                 "variables": {
                     "query": "",
                     "filters": {
                         "tagName": tag,
                         "brands": [
                             "future-social",
                             "money-with-katie",
                             "press",
                             "cfo",
                             "light-roast",
                             "sidekick",
                             "money-scoop",
                             "the-turnout",
                             "budgeting-challenge","daily",
                             "investing-challenge"
                         ]
                     },
                     "offset": 0,
                     "limit": 10}
                 }
    gql_json = utils.post_url('https://singularity.morningbrew.com/graphql', json_data=post_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')
    feed_urls = []
    for article in gql_json['data']['allStorySearch']:
        url = 'https://www.morningbrew.com/{}/stories/{}'.format(article['vertical']['slug'], article['slug'])
        feed_urls.append(url)
    return feed_urls


def get_issues_feed(args, save_debug):
    query = '''query IssuesSearch($query: String!, $newsletter: String!, $limit: Int!, $offset: Int!) {
  allArchiveIssues(
    query: $query
    newsletter: $newsletter
    limit: $limit
    offset: $offset
  ) {
    title
    subjectLine
    previewText
    websitePreviewText
    slug
    date
    __typename
  }
}
'''
    split_url = urlsplit(args['url'])
    if split_url.query:
        url_query = parse_qs(split_url.query)
        issue = url_query['v'][0]
    else:
        paths = list(filter(None, split_url.path[1:].split('/')))
        issue = paths[0]
    post_data = {"operationName": "IssuesSearch",
                 "query": query,
                 "variables": {
                     "newsletter": issue,
                     "query": "",
                     "offset": 0,
                     "limit": 10}
                 }
    gql_json = utils.post_url('https://singularity.morningbrew.com/graphql', json_data=post_data)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/feed.json')
    feed_urls = []
    for article in gql_json['data']['allArchiveIssues']:
        url = 'https://www.morningbrew.com/{}/issues/{}'.format(issue, article['slug'])
        feed_urls.append(url)
    return feed_urls


def get_feed(args, save_debug=False):
    feed_urls = []
    feed_title = ''
    if '/contributor/' in args['url']:
        feed_urls = get_author_feed(args, save_debug)
    elif '/search?tag' in args['url']:
        feed_urls = get_tag_feed(args, save_debug)
    elif '/issues/' in args['url']:
        feed_urls = get_issues_feed(args, save_debug)
    elif '/archive?v' in args['url']:
        feed_urls = get_issues_feed(args, save_debug)
    else:
        next_json = get_next_json(args['url'])
        if not next_json:
            return None
        if save_debug:
            utils.write_file(next_json, './debug/feed.json')
        apollo_state = next_json['pageProps']['initialApolloState']
        for key, val in apollo_state['ROOT_QUERY'].items():
            if key.startswith('v2Vertical'):
                feed_title = val['name']
                for it in val['recentStories']:
                    article = apollo_state[it['__ref']]
                    url = 'https://www.morningbrew.com/{}/stories/{}'.format(article['vertical']['slug'], article['slug'])
                    feed_urls.append(url)
                break
            elif key.startswith('v2Series'):
                series = apollo_state[val['__ref']]
                feed_title = 'Morning Brew | ' + series['name']
                for it in series['content']:
                    article = apollo_state[it['__ref']]
                    url = 'https://www.morningbrew.com/{}/stories/{}'.format(article['vertical']['slug'], article['slug'])
                    feed_urls.append(url)

    if not feed_urls:
        return None

    n = 0
    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed_items = []
    for url in feed_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def test_handler():
    feeds = ['https://www.morningbrew.com/daily'
             'https://www.morningbrew.com/archive?v=daily',
             'https://www.morningbrew.com/sidekick',
             'https://www.morningbrew.com/archive?v=sidekick',
             'https://www.emergingtechbrew.com/',
             'https://www.morningbrew.com/archive?v=emerging-tech']
    for url in feeds:
        get_feed({"url": url}, True)
