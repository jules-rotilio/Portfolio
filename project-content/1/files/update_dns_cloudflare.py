#!/usr/bin/env python3

import ipaddress
import os
import sys
from collections.abc import Callable
from typing import Literal

import httpx
from cloudflare import Cloudflare
from cloudflare.types.dns.record_list_params import Name
from cloudflare.types.dns.record_response import RecordResponse
from dotenv import load_dotenv

from loggers import print_error as error, print_update as update


# Set to True once the network has public IPv6 connectivity.
ENABLE_IPV6 = False

# Domain name -> Cloudflare zone ID. The apex record of each domain is kept in sync.
DOMAINS = {
    "example.com": "<your-zone-id>",
    "example.org": "<your-zone-id>",
}

AddressFamily = Literal[4, 6]
RecordType = Literal["A", "AAAA"]

RECORD_TYPES: dict[AddressFamily, RecordType] = {4: "A", 6: "AAAA"}

# Tried in order; Cloudflare's trace endpoint first, the others as fallbacks.
IP_SOURCES: dict[AddressFamily, list[str]] = {
    4: [
        "https://cloudflare.com/cdn-cgi/trace",
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    ],
    6: [
        "https://cloudflare.com/cdn-cgi/trace",
        "https://api6.ipify.org",
        "https://ifconfig.me/ip",
    ],
}


class IPDetectionError(RuntimeError):
    pass


def parse_ip(body: str, family: AddressFamily) -> str:
    """Extract an IP from a plain-text body or a Cloudflare trace (`ip=...` line)."""
    text = body.strip()
    for line in text.splitlines():
        if line.startswith("ip="):
            text = line.removeprefix("ip=").strip()
            break

    address = ipaddress.ip_address(text)
    if address.version != family:
        raise ValueError(f"expected an IPv{family} address, got '{address}'")
    return str(address)


def fetch_url(url: str, family: AddressFamily) -> str:
    # Binding to the wildcard address of a family forces the connection over it.
    local_address = "0.0.0.0" if family == 4 else "::"
    transport = httpx.HTTPTransport(local_address=local_address)
    with httpx.Client(transport=transport, timeout=10) as http:
        response = http.get(url)
        response.raise_for_status()
        return response.text


def get_public_ip(
    family: AddressFamily,
    fetch: Callable[[str, AddressFamily], str] = fetch_url,
) -> str:
    failures = []
    for url in IP_SOURCES[family]:
        try:
            return parse_ip(fetch(url, family), family)
        except (httpx.HTTPError, ValueError) as exc:
            failures.append(f"{url}: {exc}")
    raise IPDetectionError(
        f"Could not detect public IPv{family} address ({'; '.join(failures)})"
    )


def find_dns_record(
    client: Cloudflare, zone_id: str, name: str, record_type: RecordType
) -> RecordResponse | None:
    records = list(
        client.dns.records.list(
            zone_id=zone_id,
            name=Name(exact=name),
            type=record_type,
        )
    )
    if not records:
        return None
    if len(records) > 1:
        raise RuntimeError(
            f"Found {len(records)} {record_type} records for '{name}', expected one"
        )

    record = records[0]
    if record.type != record_type:
        raise RuntimeError(
            f"Expected a {record_type} record for '{name}', got {record.type}"
        )
    return record


def sync_dns_ip(
    client: Cloudflare,
    zone_id: str,
    name: str,
    record_type: RecordType,
    address: str,
) -> None:
    record = find_dns_record(client, zone_id, name, record_type)
    if record is None:
        client.dns.records.create(
            zone_id=zone_id,
            name=name,
            ttl=1,
            type=record_type,
            content=address,
        )
        update(f"Created {record_type} record for {name}: {address}")
        return

    if record.content == address:
        return

    # edit (PATCH) keeps fields we don't send, such as proxied, comment and tags.
    client.dns.records.edit(
        dns_record_id=record.id,
        zone_id=zone_id,
        name=record.name,
        ttl=record.ttl,
        type=record_type,
        content=address,
    )
    update(f"Updated {record_type} record for {name}: {record.content} -> {address}")


def main() -> int:
    load_dotenv()

    api_token = os.environ.get("CLOUDFLARE_API_TOKEN") or os.environ.get("API_KEY")
    if not api_token:
        error("No Cloudflare API token found in CLOUDFLARE_API_TOKEN or API_KEY")
        return 1

    client = Cloudflare(api_token=api_token)
    families: list[AddressFamily] = [4, 6] if ENABLE_IPV6 else [4]

    ok = True
    for family in families:
        try:
            address = get_public_ip(family)
        except IPDetectionError as exc:
            error(str(exc))
            ok = False
            continue

        record_type = RECORD_TYPES[family]
        for name, zone_id in DOMAINS.items():
            try:
                sync_dns_ip(client, zone_id, name, record_type, address)
            except Exception as exc:
                error(f"Failed to sync {record_type} record for {name}: {exc}")
                ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
