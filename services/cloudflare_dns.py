def public_dns_resolves(host):
    import dns.exception
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5.0
    for rrtype in ("A", "AAAA", "CNAME"):
        try:
            resolver.resolve(host, rrtype)
            return True
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout,
        ):
            continue
        except Exception:
            continue
    return False
