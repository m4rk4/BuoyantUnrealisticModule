import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote, quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    # https://images.newrepublic.com/a05fa3deb492e21fcba5ac09b7743e7d7e8373f5.jpeg?auto=compress&ar=3%3A2&fit=crop&crop=faces&fm=jpg&ixlib=react-9.0.2&w=1000&q=65&dpr=1
    if img_src.startswith('//'):
        img_src = 'https:' + img_src
    split_url = urlsplit(img_src)
    if split_url.query:
        m = re.search(r'\bw=\d+', img_src)
        if m:
            return re.sub(r'\bw=\d+', 'w={}'.format(width), img_src)
        else:
            return '{}&w={}'.format(img_src, width)
    return '{}?auto=compress&ar=3%3A2&fit=crop&crop=faces&fm=jpg&ixlib=react-9.0.2&w={}&q=65&dpr=1'.format(img_src, width)


def get_content(url, args, site_json, save_debug=False):
    query = '''

  query ($id: ID, $nid: ID) {
    Article(id: $id, nid: $nid) {
      ...ArticlePageFields
      feed{...ArticlePageFields}
    }
  }

  fragment ArticlePageFields on Article {
    id
    nid
    slug
    title
    cleanTitle
    badge
    frontPage {
      id
      slug
      title
    }
    LinkedSeriesId
    series {
      id
      slug
      seriesStream {
        nids
      }
      linkedArticle {
        id
        title
        url
      }
    }
    authors {
      id
      name
      slug
      blurb
      meta {
        twitter
        podcast
      }
    }
    body
    publishedAt
    displayAt
    publicPublishedDate
    status
    ledeImage {
      id
      src
      format
      width
      height
      alt
    }
    ledeAltImage {
      id
      src
      format
      width
      height
      alt
    }
    url
    urlFull
    meta {
      wordCount
      template
      navigationTheme
      bigLede
      hideLede
      cropModeFronts
      ledeOverrideSource
      disableAds
      social {
        google {
          title
          description
        }
        facebook {
          title
          description
          image {
            id
            src
            format
            width
            height
          }
        }
        twitter {
          title
          description
          image {
            id
            src
            format
            width
            height
          }
        }
      }
    }
    ledeImageCredit
    ledeImageCreditBottom
    ledeImageRealCaption
    bylines
    deck
    type
    galleries {
      id
      galleryData {
        captionText
        creditText
        image {
          id
          src
          width
          height
        }
      }
    }
    tags {
      id
      slug
      label
    }
    suppressBadges
  }
    '''
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    variables = {"nid": str(paths[1])}
    gql_url = 'https://newrepublic.com/graphql?query={}&variables={}'.format(quote(query), quote(json.dumps(variables)))
    gql_json = utils.get_url_json(gql_url)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    article_json = gql_json['data']['Article']
    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['urlFull']
    item['title'] = article_json['cleanTitle']

    dt = datetime.fromisoformat(article_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = []
    for it in article_json['authors']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if article_json.get('frontPage'):
        item['tags'].append(article_json['frontPage']['title'])
    for it in article_json['tags']:
        item['tags'].append(it['label'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if article_json.get('deck'):
        item['summary'] = article_json['deck']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['deck'])

    if article_json.get('ledeImage'):
        item['_image'] = 'https:' + article_json['ledeImage']['src']
        captions = []
        if article_json.get('ledeImageRealCaption'):
            captions.append(article_json['ledeImageRealCaption'])
        if article_json.get('ledeImageCredit'):
            captions.append(article_json['ledeImageCredit'])
        item['content_html'] += utils.add_image(resize_image(article_json['ledeImage']['src']), ' | '.join(captions))

    soup = BeautifulSoup(article_json['body'], 'html.parser')
    for el in soup.find_all(class_='article-embed'):
        new_html = ''
        if 'image-embed' in el['class']:
            img = el.find('img')
            if img:
                captions = []
                it = el.find(class_='caption')
                if it:
                    captions.append(it.get_text())
                it = el.find(class_='credit')
                if it:
                    captions.append(it.get_text())
                new_html = utils.add_image(resize_image(img['src']), ' | '.join(captions))
        elif 'book-embed' in el['class']:
            img = el.find('img')
            if img:
                new_html = '<table><tr><td><img src="{}"/></td><td>'.format(resize_image(img['src'], 200))
                it = el.find(class_='book-title')
                if it:
                    new_html += '<strong>{}</strong>'.format(it.get_text())
                it = el.find(class_='book-author')
                if it:
                    new_html += '<br/>{}'.format(it.get_text())
                it = el.find(class_='book-meta')
                if it:
                    new_html += '<br/><small>{}</small>'.format(it.get_text())
                it = el.find(class_='book-buy-link')
                if it:
                    new_html += '<br/><a href="{}">{}</a>'.format(it['href'], it.get_text())
                new_html += '</td></tr></table>'
        elif el.find(class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find(class_='podcastButtons'):
            el.decompose()
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(it['src'])
        if el.name:
            if new_html:
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()
            else:
                logger.warning('unhandled article-embed in ' + item['url'])

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    if args['url'].endswith('rss.xml'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    query = ''
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0:
        if paths[0] == 'magazine':
            title = 'The New Republic | The Magazine'
            gql_json = utils.get_url_json('https://newrepublic.com/api/content/magazine')
            if not gql_json:
                return None
            if save_debug:
                utils.write_file(gql_json, './debug/feed.json')
            articles = []
            for key, val in gql_json['data'].items():
                if isinstance(val, list):
                    for article in val:
                        if article.get('url'):
                            articles.append(article)

        else:
            query = '''
query ($query: ArticlesListQuery) {
  articlesList(query: $query) {
    totalHits
    nids
    articles {
      ...ArticleListFields
      __typename
    }
    __typename
  }
}

fragment ArticleListFields on Article {
  id
  nid
  url
  updatedAt
  publishedAt
  publicPublishedDate
  type
  meta {
    cropModeFronts
    __typename
  }
  ledeImage {
    id
    src
    format
    alt
    height
    width
    __typename
  }
  frontPage {
    id
    title
    slug
    __typename
  }
  status
  title
  lock {
    id
    UserId
    updatedAt
    user {
      id
      name
      __typename
    }
    __typename
  }
  authors {
    id
    name
    slug
    __typename
  }
  __typename
}
            '''
            if paths[0] == 'authors':
                variables = {"query":{"authorSlug":paths[1],"page":1}}
                title = 'The New Republic | ' + paths[1].replace('-', ' ').title()
            elif paths[0] == 'tags':
                variables = {"query":{"tagSlug":paths[1],"page":1}}
                title = 'The New Republic | ' + paths[1].replace('-', ' ').title()
            elif len(paths) == 1:
                variables = {"query":{"tagSlug":paths[0],"page":1}}
                title = 'The New Republic | ' + paths[0].replace('-', ' ').title()
            else:
                logger.warning('unhandled feed url ' + args['url'])
                return None
            gql_url = 'https://newrepublic.com/graphql?query={}&variables={}'.format(quote_plus(query), quote_plus(json.dumps(variables)))
            gql_json = utils.get_url_json(gql_url)
            if not gql_json:
                return None
            if save_debug:
                utils.write_file(gql_json, './debug/feed.json')
            articles = gql_json['data']['articlesList']['articles']

    n = 0
    feed = utils.init_jsonfeed(args)
    feed['title'] = title
    feed_items = []
    for article in articles:
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['url'])
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
