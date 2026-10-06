"""Group only human-reviewed catalog images; never infer identity from similarity."""
import hashlib
import json
from pathlib import Path


class ReviewedProductGroups:
    def __init__(self, groups=()):
        self.groups = {g['group_id']: g['members'] for g in groups}
        self.by_product = {m['product_id']: gid for gid, members in self.groups.items() for m in members}

    @classmethod
    def load(cls, path, catalog_items, catalog_dir):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('schema_version') != '1.0' or data.get('basis') != 'human_visual_review':
            raise ValueError('Unsupported reviewed grouping manifest')
        groups = data.get('groups')
        if not isinstance(groups, list):
            raise ValueError('Reviewed groups must be a list')
        by_id = {item['product_id']: item for item in catalog_items.values()}
        if len(by_id) != len(catalog_items):
            raise ValueError('Catalog image IDs must be unique')
        seen_ids, seen_groups = set(), set()
        for group in groups:
            gid, members = group.get('group_id'), group.get('members')
            if not isinstance(gid, str) or not gid or gid in seen_groups:
                raise ValueError('Missing or duplicate group ID')
            seen_groups.add(gid)
            if not isinstance(members, list) or len(members) < 2:
                raise ValueError('A reviewed group needs at least two images')
            categories = set()
            for member in members:
                pid = member.get('product_id')
                if pid not in by_id or pid in seen_ids:
                    raise ValueError('Unknown or overlapping reviewed image ID')
                seen_ids.add(pid)
                item = by_id[pid]
                if member.get('image') != item['image']:
                    raise ValueError('Reviewed image path differs from catalog metadata')
                image_path = (Path(catalog_dir) / item['image']).resolve()
                if not image_path.is_relative_to(Path(catalog_dir).resolve()):
                    raise ValueError('Reviewed image is outside catalog')
                if hashlib.sha256(image_path.read_bytes()).hexdigest() != member.get('sha256'):
                    raise ValueError('Reviewed image bytes changed')
                categories.add(item['category_key'])
            if len(categories) != 1:
                raise ValueError('Reviewed group spans different categories')
        return cls(groups)

    def select(self, ranked_results, top_k):
        if top_k < 1:
            raise ValueError('top_k must be positive')
        selected, seen = [], set()
        for result in ranked_results:
            pid = result['product_id']
            gid = self.by_product.get(pid)
            key = ('group', gid) if gid else ('image', pid)
            if key in seen:
                continue
            seen.add(key)
            representative = dict(result)
            if gid:
                representative['reviewed_group_id'] = gid
                representative['group_images'] = [dict(m, url='/catalog/' + m['image']) for m in self.groups[gid]]
            selected.append(representative)
            if len(selected) == top_k:
                break
        return selected
