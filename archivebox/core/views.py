__package__ = 'archivebox.core'

from io import StringIO
from contextlib import redirect_stdout

from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404
from django.utils.html import format_html, mark_safe
from django.views import View, static
from django.views.generic.list import ListView
from django.views.generic import FormView
from django.db.models import Q
from django.contrib.auth.mixins import UserPassesTestMixin

from core.models import Snapshot
from core.forms import AddLinkForm

from ..config import (
    OUTPUT_DIR,
    PUBLIC_INDEX,
    PUBLIC_SNAPSHOTS,
    PUBLIC_ADD_VIEW,
    VERSION,
    FOOTER_INFO,
    SNAPSHOTS_PER_PAGE,
)
from main import add
from ..util import base_url, ansi_to_html
from ..index.html import snapshot_icons


class HomepageView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('/admin/core/snapshot/')

        if PUBLIC_INDEX:
            return redirect('/public')
        
        return redirect(f'/admin/login/?next={request.path}')


class SnapshotView(View):
    # render static html index from filesystem archive/<timestamp>/index.html

    def get(self, request, path):
        if not request.user.is_authenticated and not PUBLIC_SNAPSHOTS:
            return redirect(f'/admin/login/?next={request.path}')

        try:
            slug, archivefile = path.split('/', 1)
        except (IndexError, ValueError):
            slug, archivefile = path.split('/', 1)[0], 'index.html'

        # slug is a timestamp
        if slug.replace('.','').isdigit():

            # missing trailing slash -> redirect to index
            if '/' not in path:
                return redirect(f'{path}/index.html')

            try:
                try:
                    snapshot = Snapshot.objects.get(timestamp=slug)
                    response = static.serve(request, archivefile, document_root=snapshot.link_dir, show_indexes=True)
                    response["Link"] = f'<{snapshot.url}>; rel="canonical"'
                    return response
                except Snapshot.DoesNotExist:
                    if Snapshot.objects.filter(timestamp__startswith=slug).exists():
                        raise Snapshot.MultipleObjectsReturned
                    else:
                        raise
            except Snapshot.DoesNotExist:
                # Snapshot does not exist
                return HttpResponse(
                    format_html(
                        (
                            '<center><br/><br/><br/>'
                            'No Snapshots match the given timestamp or UUID: <code>{}</code><br/><br/>'
                            'You can <a href="/add/" target="_top">add a new Snapshot</a>, or return to the <a href="/" target="_top">Main Index</a>'
                            '</center>'
                        ),
                        slug,
                        path,
                    ),
                    content_type="text/html",
                    status=404,
                )
            except Snapshot.MultipleObjectsReturned:
                snapshot_hrefs = mark_safe('<br/>').join(
                    format_html(
                        '{} <a href="/archive/{}/index.html"><b><code>{}</code></b></a> {} <b>{}</b>',
                        snap.added.strftime('%Y-%m-%d %H:%M:%S'),
                        snap.timestamp,
                        snap.timestamp,
                        snap.url,
                        snap.title or '',
                    )
                    for snap in Snapshot.objects.filter(timestamp__startswith=slug).only('url', 'timestamp', 'title', 'added').order_by('-added')
                )
                return HttpResponse(
                    format_html(
                        (
                            'Multiple Snapshots match the given timestamp/UUID <code>{}</code><br/><pre>'
                        ),
                        slug,
                    ) + snapshot_hrefs + format_html(
                        (
                            '</pre><br/>'
                            'Choose a Snapshot to proceed or go back to the <a href="/" target="_top">Main Index</a>'
                        )
                    ),
                    content_type="text/html",
                    status=404,
                )
            except Http404:
                # Snapshot dir exists but file within does not e.g. 124235.324234/screenshot.png
                return HttpResponse(
                    format_html(
                        (
                            '<center><br/><br/><br/>'
                            '<a href="/archive/{}/index.html" target="_top">Snapshot <b><code>{}</code></b></a> exists but no file or folder <b><code>/{}</code></b> exists within.<br/><br/>'
                            '<small>Maybe this output type is not availabe for this URL,<br/>or the archiving process has not completed for this Snapshot yet?<br/>'
                            '<pre><code># run this cmd to finish archiving this Snapshot<br/>archivebox update -t timestamp {}</code></pre></small><br/><br/>'
                            'You can go back to the <a href="/archive/{}/index.html" target="_top">Snapshot <b><code>{}</code></b></a> detail page, or return to the <a href="/" target="_top">Main Index</a>'
                            '</center>'
                        ),
                        snapshot.timestamp,
                        snapshot.timestamp,
                        archivefile,
                        snapshot.timestamp,
                        snapshot.timestamp,
                        snapshot.timestamp,
                    ),
                    content_type="text/html",
                    status=404,
                )
        # slug is a URL
        try:
            try:
                # try exact match on full url first
                snapshot = Snapshot.objects.get(
                    Q(url='http://' + path) | Q(url='https://' + path)
                )
            except Snapshot.DoesNotExist:
                # fall back to match on exact base_url
                try:
                    snapshot = Snapshot.objects.get(
                        Q(url='http://' + base_url(path)) | Q(url='https://' + base_url(path))
                    )
                except Snapshot.DoesNotExist:
                    # fall back to matching base_url as prefix
                    snapshot = Snapshot.objects.get(
                        Q(url__startswith='http://' + base_url(path)) | Q(url__startswith='https://' + base_url(path))
                    )
            return redirect(f'/archive/{snapshot.timestamp}/index.html')
        except Snapshot.DoesNotExist:
            return HttpResponse(
                format_html(
                    (
                        '<center><br/><br/><br/>'
                        'No Snapshots match the given url: <code>{}</code><br/><br/><br/>'
                        'Return to the <a href="/" target="_top">Main Index</a>, or:<br/><br/>'
                        '+ <i><a href="/add/?url={}" target="_top">Add a new Snapshot for <code>{}</code></a><br/><br/></i>'
                        '</center>'
                    ),
                    base_url(path),
                    path if '://' in path else f'https://{path}',
                    path,
                ),
                content_type="text/html",
                status=404,
            )
        except Snapshot.MultipleObjectsReturned:
            snapshot_hrefs = mark_safe('<br/>').join(
                format_html(
                    '{} <a href="/archive/{}/index.html"><b><code>{}</code></b></a> {} <b>{}</b>',
                    snap.added.strftime('%Y-%m-%d %H:%M:%S'),
                    snap.timestamp,
                    snap.timestamp,
                    snap.url,
                    snap.title or '',
                )
                for snap in Snapshot.objects.filter(
                    Q(url__startswith='http://' + base_url(path)) | Q(url__startswith='https://' + base_url(path))
                ).only('url', 'timestamp', 'title', 'added').order_by('-added')
            )
            return HttpResponse(
                format_html(
                    (
                        'Multiple Snapshots match the given URL <code>{}</code><br/><pre>'
                    ),
                    base_url(path),
                ) + snapshot_hrefs + format_html(
                    (
                        '</pre><br/>'
                        'Choose a Snapshot to proceed or go back to the <a href="/" target="_top">Main Index</a>'
                    )
                ),
                content_type="text/html",
                status=404,
            )
        

class PublicIndexView(ListView):
    template_name = 'public_index.html'
    model = Snapshot
    paginate_by = SNAPSHOTS_PER_PAGE
    ordering = ['title']

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            'VERSION': VERSION,
            'FOOTER_INFO': FOOTER_INFO,
        }

    def get_queryset(self, **kwargs): 
        qs = super().get_queryset(**kwargs)
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(url__icontains=query) | Q(timestamp__icontains=query) | Q(tags__name__icontains=query))
        
        for snapshot in qs:
            # lazy load snapshot icons, otherwise it will load icons for entire index at once
            snapshot.icons = lambda: snapshot_icons(snapshot)
        return qs

    def get(self, *args, **kwargs):
        if PUBLIC_INDEX or self.request.user.is_authenticated:
            response = super().get(*args, **kwargs)
            return response
        else:
            return redirect(f'/admin/login/?next={self.request.path}')


class AddView(UserPassesTestMixin, FormView):
    template_name = "add.html"
    form_class = AddLinkForm

    def get_initial(self):
        """Prefill the AddLinkForm with the 'url' GET parameter"""
        if self.request.method == 'GET':
            url = self.request.GET.get('url', None)
            if url:
                return {'url': url if '://' in url else f'https://{url}'}
        
        return super().get_initial()

    def test_func(self):
        return PUBLIC_ADD_VIEW or self.request.user.is_authenticated

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            'title': "Add URLs",
            # We can't just call request.build_absolute_uri in the template, because it would include query parameters
            'absolute_add_path': self.request.build_absolute_uri(self.request.path),
            'VERSION': VERSION,
            'FOOTER_INFO': FOOTER_INFO,
            'stdout': '',
        }

    def form_valid(self, form):
        url = form.cleaned_data["url"]
        print(f'[+] Adding URL: {url}')
        depth = 0 if form.cleaned_data["depth"] == "0" else 1
        extractors = ','.join(form.cleaned_data["archive_methods"])
        input_kwargs = {
            "urls": url,
            "depth": depth,
            "update_all": False,
            "out_dir": OUTPUT_DIR,
        }
        if extractors:
            input_kwargs.update({"extractors": extractors})
        add_stdout = StringIO()
        with redirect_stdout(add_stdout):
            add(**input_kwargs)
            print(add_stdout.getvalue())

        context = self.get_context_data()

        context.update({
            "stdout": ansi_to_html(add_stdout.getvalue().strip()),
            "form": AddLinkForm()
        })
        return render(template_name=self.template_name, request=self.request, context=context)
