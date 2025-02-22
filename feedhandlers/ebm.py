import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    if img_src.startswith('https://img.'):
        # return utils.clean_url(img_src) + '?auto=format%2Ccompress&w={}'.format(width)
        return utils.clean_url(img_src) + '?auto=format%2Ccompress&fit=max&q=75&w=' + str(width)
    elif img_src.startswith('https://cdn.'):
        return re.sub(r'\/\d+w\/', '/{}w/'.format(width), img_src)
    else:
        return img_src


def get_content(url, args, site_json, save_debug=False):
    # Content sites: https://www.endeavorbusinessmedia.com/mkts-we-serve/
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    gql_data = {
        "query": "query getWebsiteLayoutPage(\n  $alias: String!\n  $useCache: Boolean\n  $preview: Boolean\n  $cacheKey: String\n) {\n  getWebsiteLayoutPage(\n    input: { alias: $alias, useCache: $useCache, preview: $preview, cacheKey: $cacheKey }\n  ) {\n    id\n    name\n    module\n    type\n    alias\n    contentTypes\n    pageType\n    isGlobal\n    tenants\n    propagate\n    hideHeader\n    hideFooter\n    key\n    loadMoreType {\n      type\n    }\n    primaryGrid\n    secondaryGrid\n    excludeAds {\n      welcomeAd\n      headerLeaderboardAd\n      stickyLeaderboardAd\n      contentBodyNativeAd\n      contentBodyEmbedAd\n      contentListNativeAd\n      reskinAd\n    }\n    pageData\n    cache\n    created\n    usedContentIds\n    usedIssueIds\n  }\n}",
        "variables": {
            "alias": split_url.path,
            "useCache": True,
            "preview": False,
            "cacheKey":"v2.5"
        }
    }
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Not A(Brand\";v=\"8\", \"Chromium\";v=\"132\", \"Microsoft Edge\";v=\"132\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
        "x-tenant-key": site_json['x-tenant-key']
    }
    gql_json = utils.post_url(site_json['graphql_url'], json_data=gql_data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')

    page_data = gql_json['data']['getWebsiteLayoutPage']['pageData']
    if page_data['type'] == 'content':
        gql_data = {
            "query": "query GetContent($id: Int!, $status: ModelStatus, $requirePublished: Boolean) {\n  getContent(input: { id: $id, status: $status, requirePublished: $requirePublished }) {\n    __typename\n    id\n    name\n    seoTitle\n    shortName\n    type\n    teaser(input: { useFallback: true, maxLength: 175 })\n    explicitTeaser: teaser(input: { useFallback: false, maxLength: null })\n    bodyBlocks\n    publishedDate\n    published\n    labels\n    layout\n    metadata {\n      title\n      aiKeywords\n      aiIndustries\n    }\n    relatedContent(input: { queryTypes: [owned] }) {\n      edges {\n        node {\n          id\n          type\n        }\n      }\n    }\n    siteContext {\n      path\n      canonicalUrl\n      url\n    }\n    company {\n      id\n      name\n      alias\n      enableRmi\n    }\n    primarySection {\n      id\n      name\n      fullName\n      alias\n      canonicalPath\n      gamAlias\n      hierarchy {\n        id\n        name\n        alias\n        canonicalPath\n      }\n    }\n    membership {\n      id\n      additionalUserDemographicFields\n      alias\n      completeRegistrationPageText\n      emailConfirmationReminderText\n      emailConfirmationText\n      features\n      gatedContentPreviewText\n      isFree\n      joinButtonLabel\n      joinButtonText\n      missingProductMessage\n      omedaProduct\n      omedaProductName\n      omedaProductVersion\n      omedaPromoCode\n      overviewText\n      paymentFormURL\n      payNowButtonLabel\n      payNowButtonText\n      requiredUserCommonFields\n      requiredUserDemographicFields\n      status\n      title\n    }\n    taxonomy(input: { pagination: { limit: 50 } }) {\n      edges {\n        node {\n          id\n          type\n          name\n          fullName\n        }\n      }\n    }\n    primaryImage {\n      id\n      src\n      alt\n      caption\n      credit\n      isLogo\n      displayName\n    }\n    gating {\n      surveyType\n      surveyId\n    }\n    userRegistration {\n      isRequired\n      accessLevels\n    }\n    websiteSchedules {\n      section {\n        id\n        name\n        alias\n      }\n      option {\n        id\n        name\n      }\n    }\n    images(input: { pagination: { limit: 100 } }) {\n      edges {\n        node {\n          id\n          name\n          src\n          credit\n          caption\n          alt\n          body\n          isLogo\n          displayName\n          approvedWebsite\n          approvedMagazine\n        }\n      }\n    }\n    ... on ContentArticle {\n      sidebars\n    }\n    ... on ContentVideo {\n      embedCode\n    }\n    ... on ContentNews {\n      source\n      byline\n    }\n    ... on ContentEvent {\n      endDate\n      startDate\n      venue {\n        id\n        addresses {\n          address1\n          address2\n          city\n          region\n          country\n          postalCode\n          primary\n        }\n        name\n      }\n    }\n    ... on ContentContact {\n      fullName\n      body\n      title\n      website\n      socialLinks {\n        provider\n        url\n        label\n      }\n    }\n    ... on ContentPromotion {\n      linkUrl\n      crawlUrl\n    }\n    ... on ContentDocument {\n      fileName\n      filePath\n      downloadAttachment {\n        id\n        fileName\n        src\n      }\n    }\n    ... on ContentPodcast {\n      fileName\n      filePath\n      downloadAttachment {\n        id\n        fileName\n        src\n      }\n    }\n    ... on ContentWhitepaper {\n      fileName\n      filePath\n      downloadAttachment {\n        id\n        fileName\n        src\n      }\n    }\n    ... on ContentWebinar {\n      linkUrl\n      startDate\n      duration\n      sponsors {\n        edges {\n          node {\n            id\n            name\n            path\n          }\n        }\n      }\n    }\n    ... on Addressable {\n      address1\n      address2\n      city\n      state\n      zip\n      cityStateZip\n      country\n    }\n    ... on Contactable {\n      phone\n      tollfree\n      fax\n      website\n      title\n      mobile\n      publicEmail\n    }\n    ... on ContentCompany {\n      website\n      address1\n      address2\n      city\n      state\n      zip\n      phone\n      fax\n      enableRmi\n      numberOfEmployees\n      productSummary\n      yearsInOperation\n      tollfree\n      publicEmail\n      publicContacts {\n        edges {\n          node {\n            id\n            fullName\n            title\n            email\n            publicEmail\n            primaryImage {\n              src\n              alt\n              caption\n              credit\n            }\n          }\n        }\n      }\n      socialLinks {\n        provider\n        url\n        label\n      }\n      youtube {\n        username\n        channelId\n        playlistId\n      }\n      youtubeVideos(input: { pagination: { limit: 10 } }) {\n        edges {\n          node {\n            id\n            thumbnail\n            description\n            published\n            title\n            url\n          }\n        }\n      }\n      youtubeUrl\n    }\n    ... on SocialLinkable {\n      socialLinks {\n        provider\n        url\n        label\n      }\n    }\n    ... on Media {\n      fileSrc\n    }\n    ... on Inquirable {\n      enableRmi\n    }\n    ... on Authorable {\n      authors {\n        edges {\n          node {\n            id\n            name\n            title\n            type\n            alias\n          }\n        }\n      }\n      contributors {\n        edges {\n          node {\n            id\n            name\n            type\n          }\n        }\n      }\n      photographers {\n        edges {\n          node {\n            id\n            name\n            type\n          }\n        }\n      }\n    }\n  }\n}",
            "variables": {
                "id": page_data['contentId'],
                "status": "active",
                "requirePublished": True
            }
        }
        gql_json = utils.post_url(site_json['graphql_url'], json_data=gql_data, headers=headers)
        if not gql_json:
            return None
        if save_debug:
            utils.write_file(gql_json, './debug/debug.json')
        page_data = gql_json['data']['getContent']

    item = {}
    item['id'] = page_data['id']
    item['url'] = page_data['siteContext']['canonicalUrl']
    item['title'] = page_data['name']

    dt = datetime.fromtimestamp(page_data['published']/1000).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if page_data.get('updated'):
        dt = datetime.fromtimestamp(page_data['updated']/1000).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    authors = []
    if page_data.get('authors'):
        for it in page_data['authors']['edges']:
            authors.append(it['node']['name'])
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = split_url.netloc

    item['tags'] = []
    if page_data.get('taxonomy') and page_data['taxonomy'].get('edges'):
        item['tags'] += [x['node']['name'] for x in page_data['taxonomy']['edges']]
    if page_data['metadata'].get('aiKeywords'):
        item['tags'] += page_data['metadata']['aiKeywords'].copy()
    # if page_data['metadata'].get('aiIndustries'):
    #     item['tags'] += page_data['metadata']['aiIndustries'].copy()
    if len(item['tags']) == 0:
        del item['tags']

    if page_data.get('teaser'):
        item['summary'] = page_data['teaser']

    item['content_html'] = ''
    if page_data.get('deck'):
        item['content_html'] += '<p><em>{}</em></p>'.format(page_data['deck'])

    if page_data.get('primaryImage'):
        item['_image'] = page_data['primaryImage']['src']
        if page_data['__typename'] != 'ContentMediaGallery' and page_data['__typename'] != 'ContentVideo':
            captions = []
            if page_data['primaryImage'].get('caption'):
                captions.append(page_data['primaryImage']['caption'])
            if page_data['primaryImage'].get('credit'):
                captions.append(page_data['primaryImage']['credit'])
            item['content_html'] += utils.add_image(resize_image(page_data['primaryImage']['src']), ' | '.join(captions))

    if page_data['__typename'] == 'ContentVideo' and page_data.get('embedCode'):
        soup = BeautifulSoup(page_data['embedCode'], 'html.parser')
        item['content_html'] += utils.add_embed(soup.iframe['src'])

    def sub_embed_content(matchobj):
        data_json = {}
        for m in re.findall(r'([^=\s]+)="([^"]+)"', matchobj.group(1)):
            data_json[m[0]] = m[1]
        if data_json.get('data-embed-type') == 'image':
            captions = []
            if data_json.get('data-embed-caption'):
                captions.append(data_json['data-embed-caption'])
            if data_json.get('data-embed-credit'):
                captions.append(data_json['data-embed-credit'])
            return '</p>' + utils.add_image(resize_image(data_json['data-embed-src']), ' | '.join(captions)) + '<p>'
        elif data_json.get('data-embed-type') == 'oembed':
            return '</p>' + utils.add_embed(data_json['data-embed-id']) + '<p>'
        logger.warning('unhandled embed content')
        return matchobj.group(0)

    if page_data.get('bodyBlocks'):
        for block in page_data['bodyBlocks']:
            if block['type'] == 'content':
                # Related article links
                continue
            elif block['type'] == 'image':
                captions = []
                if block['data']['image'].get('caption'):
                    captions.append(block['data']['image']['caption'])
                if block['data']['image'].get('credit'):
                    captions.append(block['data']['image']['credit'])
                img_src = resize_image(block['data']['image']['src'])
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

            if block['settings'].get('text'):
                # content = re.sub(r'%{\[\s?(.*?)\s?\]}%', sub_embed_content, block['settings']['text'])
                content = block['settings']['text']
                soup = BeautifulSoup(content, 'html.parser')
                # for el in soup.find_all('img', attrs={"alt": True}):
                #     new_html = utils.add_image(resize_image(el['src']))
                #     new_el = BeautifulSoup(new_html, 'html.parser')
                #     el.insert_after(new_el)
                #     if el.parent and el.parent.name == 'p':
                #         el_parent = el.parent
                #         el.decompose()
                #         new_html = re.sub(r'(<figure .*?</figure>)', r'</p>\1<p>', str(el_parent))
                #         new_el = BeautifulSoup(new_html, 'html.parser')
                #         el_parent.insert_after(new_el)
                #         el_parent.decompose()
                #     else:
                #         el.decompose()

                for el in soup.find_all('iframe'):
                    if el.get('src'):
                        new_html = utils.add_embed(el['src'])
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        it = el.find_parent(class_='emb-video')
                        if it:
                            el_parent = it
                        elif el.parent and el.parent.name == 'p':
                            el_parent = el.parent
                        else:
                            el_parent = el
                        el_parent.insert_after(new_el)
                        el_parent.decompose()
                    elif el.get('name') and re.search(r'google_ads_iframe', el['name']):
                        it = el.find_parent('p')
                        if it:
                            it.decompose()
                        else:
                            el.decompose()
                    else:
                        logger.warning('unhandled iframe in ' + item['url'])

                for el in soup.find_all('blockquote'):
                    el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

                for el in soup.find_all('h5'):
                    el.name = 'h3'

                for el in soup.find_all('aside'):
                    el.decompose()

                item['content_html'] += str(soup)

            if block['settings'].get('sidebarHtml'):
                item['content_html'] += '<blockquote style="border-left:3px solid light-dark(#ccc, #333); margin:1.5em 10px; padding:0.5em 10px;">' + block['settings']['sidebarHtml'] + '</blockquote>'

            if block['type'] != 'text' and block['type'] != 'sidebar' and block['type'] != 'image':
                logger.warning('unhandled bodyBlock type {} in {}'.format(block['type'], item['url']))

    if page_data['__typename'] == 'ContentMediaGallery' and page_data.get('images'):
        item['content_html'] += '<h2><a href="{}/gallery?url={}" target="_blank">View Gallery</a></h2>'.format(config.server, quote_plus(item['url']))
        item['_gallery'] = []
        for i in range(1, len(page_data['images']['edges'])):
            it = page_data['images']['edges'][i]['node']
            img_src = resize_image(it['src'])
            thumb = resize_image(it['src'], 640)
            if it.get('credit'):
                caption = it['credit']
            else:
                caption = ''
            desc = ''
            if it.get('displayName'):
                desc += '<h3>{}</h3>'.format(it['displayName'])
            if it.get('body'):
                desc += '<p>{}</p>'.format(it['body'])
            elif it.get('caption'):
                desc += '<p>{}</p>'.format(it['caption'])
            item['content_html'] += utils.add_image(img_src, caption, desc=desc)
            item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb, "desc": desc})

    #item['content_html'] = re.sub(r'</figure>(\s*[^<])', r'</figure><div>&nbsp;</div>\1', item['content_html'])
    item['content_html'] = re.sub(r'<p>\s*(<br/>)?</p>', '', item['content_html'])
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
