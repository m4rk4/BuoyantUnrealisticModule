import html, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)

def get_next_json(url):
  sites_json = utils.read_json_file('./sites.json')
  next_url = 'https://hackernoon.com/_next/data/' + sites_json['hackernoon']['buildId']

  split_url = urlsplit(url)
  if split_url.path:
    next_url += split_url.path + '.json'
  else:
    next_url += '/index.json'

  next_json = utils.get_url_json(next_url, retries=1)
  if not next_json:
    logger.debug('updating hackernoon.com buildId...')
    article_html = utils.get_url_html(url)
    m = re.search(r'"buildId":"([^"]+)"', article_html)
    if m:
      logger.debug('...' + m.group(1))
      sites_json['hackernoon']['buildId'] = m.group(1)
      utils.write_file(sites_json, './sites.json')
      next_json = utils.get_url_json('https://hackernoon.com/_next/data/{}{}.json'.format(m.group(1), split_url.path))
      if not next_json:
        return None
  return next_json

def get_content(url, args, save_debug):
  next_json = get_next_json(url)
  if not next_json:
    return None
  if save_debug:
    utils.write_file(next_json, './debug/debug.json')

  if next_json['pageProps'].get('__N_REDIRECT'):
    return get_content('https://hackernoon' + next_json['pageProps']['__N_REDIRECT'], args, save_debug)

  article_json = next_json['pageProps']['data']
  item = {}
  item['id'] = article_json['id']
  item['url'] = url
  item['title'] = article_json['title']

  dt = datetime.fromtimestamp(article_json['publishedAt'])
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

  # Check age
  if args.get('age'):
    if not utils.check_age(item, args):
      return None

  item['author'] = {"name": article_json['profile']['displayName']}
  item['tags'] = article_json['tags'].copy()
  item['_image'] = article_json['mainImage']

  if article_json.get('tldr'):
    item['summary'] = article_json['tldr']

  if article_json.get('markdown'):
    md = article_json['markdown']
  elif article_json.get('markup'):
    md = article_json['markup']
  else:
    logger.warning('no markdown content in ' + url)
    return item

  md = re.sub(r':::info\n+(.+?)\n+:::', r'> ***&#x24D8;&nbsp;Info:***\n\1\n\n', md, flags=re.S)
  md = re.sub(r':::tip\n+(.+?)\n+:::', r'> ***&#x2605;&nbsp;Tip:***\n\1\n\n', md, flags=re.S)

  # This fixes lists being nested, but probably breaks actual nested lists
  md = md.replace('\n\n  \\\n', '\n\n\\\n')

  md = re.sub(r'\\\n|\\n', '', md, flags=re.S)
  def sub_underline(matchobj):
    return '<u>{}</u>'.format(matchobj.group(1))
  md = re.sub(r'__(.+?)__', sub_underline, md, flags=re.S)
  def sub_mark(matchobj):
    return '<mark style="background:rgb(156, 255, 163);">{}</mark>'.format(matchobj.group(1))
  md = re.sub(r'==(.+?)==', sub_mark, md, flags=re.S)

  soup = BeautifulSoup(markdown(md, extras=['break-on-newline', 'code-friendly', 'fenced-code-blocks', 'tables']), 'html.parser')
  for el in soup.find_all(class_='paragraph'):
    el.name = 'p'
    el.attrs = {}

  # unnest blockquotes
  for el in soup.find_all('blockquote'):
    for it in el.find_all('blockquote'):
      it.unwrap()

  for el in soup.find_all('blockquote'):
    if el.p:
      quote = ''
      for it in el.find_all('p'):
        if quote:
          quote += '<br/><br/>'
        quote += utils.bs_get_inner_html(it)
    else:
      quote = utils.bs_get_inner_html(el)
    new_html = utils.add_blockquote(quote)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all(class_='youtube-container'):
    new_html = utils.add_embed(el.iframe['src'])
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all(class_='image-container'):
    if el.img.get('alt'):
      caption = el.img['alt']
    else:
      caption = ''
    new_html = utils.add_image(el.img['src'], caption)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all('img'):
    if not el.parent.name == 'figure':
      if el.get('alt'):
        caption = el['alt']
      else:
        caption = ''
    new_html = utils.add_image(el['src'], caption)
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all(class_='tweet-container'):
    it = el.find(class_='tweet')
    new_html = utils.add_embed(utils.get_twitter_url(it['tweetid']))
    el.insert_after(BeautifulSoup(new_html, 'html.parser'))
    el.decompose()

  for el in soup.find_all('pre'):
    if el.parent and el.parent.get_text() != el.get_text():
      el.unwrap()
  #  el['style'] = 'margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;'

  for el in soup.find_all(class_='code-container'):
    if el.pre:
      el.pre['style'] = 'margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;'
    el.unwrap()

  for el in soup.find_all(class_='gist-container'):
    m = re.search(r'gist-(\w+)', el.iframe['id'])
    if m:
      gist_id = m.group(1)
      gist_js = utils.get_url_html('https://gist.github.com/{}.js'.format(gist_id))
      if gist_js:
        m = re.search(r'https:\/\/gist\.github\.com\/([^\/]+)\/{}\/raw'.format(gist_id), gist_js)
        if m:
          user = m.group(1)
          gist = utils.get_url_html(m.group(0))
          if gist:
            new_html = '<h4>Gist: <a href="https://gist.github.com/{0}/{1}">https://gist.github.com/{0}/{1}</a></h4><pre style="margin-left:2em; padding:0.5em; white-space:pre-wrap; background:#F2F2F2;">{2}</pre>'.format(user, gist_id, html.escape(gist))
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

  for el in soup.find_all(class_='not-paragraph'):
    if el.find(class_='slogging'):
      desc = ''
      user = el.find(class_='user')
      if user and user.get_text().strip():
        if user.a:
          desc += '<a href="{}"><b>{}</b></a>'.format(user.a['href'], user.get_text())
        else:
          desc += '<b>{}</b>'.format(user.get_text())
      it = el.find(class_='timestamp')
      if it and it.get_text().strip():
        desc += '<br/><small>{}</small>'.format(it.get_text())
      if desc:
        if user.a:
          new_html = '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><div>{}</div><div style="clear:left;"></div>'.format(user.a['href'], el.img['src'], desc)
        else:
          new_html = '<div><img style="float:left; margin-right:8px;" src="{}"/><div>{}</div><div style="clear:left;"></div>'.format(el.img['src'], desc)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
      el.decompose()

  for el in soup.find_all(class_='Divider'):
    if not el.get_text().strip():
      el.decompose()

  # The first row of the table is interpreted as a header and defaults to centered
  for el in soup.find_all('thead'):
    el['align'] = 'left'

  item['content_html'] = utils.add_image(item['_image'])
  item['content_html'] += str(soup)
  return item

def get_feed(args, save_debug):
  # Only https://hackernoon.com/feed
  if args['url'].endswith('/feed'):
    return rss.get_feed(args, save_debug, get_content)

  n = 0
  m = re.search('\/tagged/([-\w]+)', args['url'])
  if m:
    sites_json = utils.read_json_file('./sites.json')
    query_url = 'https://{}-dsn.algolia.net/1/indexes/*/queries?x-algolia-agent=Algolia%20for%20JavaScript%20(4.1.0)%3B%20Browser%20(lite)%3B%20JS%20Helper%20(3.5.5)%3B%20react%20(17.0.2)%3B%20react-instantsearch%20(6.12.1)&x-algolia-api-key={}&x-algolia-application-id={}'.format(sites_json['hackernoon']['x-algolia-application-id'], sites_json['hackernoon']['x-algolia-api-key'], sites_json['hackernoon']['x-algolia-application-id'].upper())
    query = '{{"requests":[{{"indexName":"stories","params":"highlightPreTag=%3Cais-highlight-0000000000%3E&highlightPostTag=%3C%2Fais-highlight-0000000000%3E&query=&maxValuesPerFacet=10&hitsPerPage=11&clickAnalytics=true&page=0&facets=%5B%22tags%22%5D&tagFilters=&facetFilters=%5B%22tags%3A{}%22%5D"}}]}}'.format(m.group(1))
    query_json = utils.post_url(query_url, query)
    if not query_json:
      return None
    if save_debug:
      utils.write_file(query_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    for article in query_json['results'][0]['hits']:
      article_url = 'https://hackernoon.com/' + article['slug']
      if save_debug:
        logger.debug('getting content from ' + article_url)
      item = get_content(article_url, args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          feed['items'].append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break

  elif '/u/' in args['url']:
    next_json = get_next_json(args['url'])
    if not next_json:
      return None
    if save_debug:
      utils.write_file(next_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    for article in next_json['pageProps']['data']['profileStories']:
      article_url = 'https://hackernoon.com/' + article['slug']
      if save_debug:
        logger.debug('getting content from ' + article_url)
      item = get_content(article_url, args, save_debug)
      if item:
        if utils.filter_item(item, args) == True:
          feed['items'].append(item)
          n += 1
          if 'max' in args:
            if n == int(args['max']):
              break
  return feed