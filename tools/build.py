import html, re, json, subprocess, os, shutil
from pathlib import Path
TOOLS = Path(__file__).resolve().parent
SRC = str(TOOLS / 'src'); OUT = str(TOOLS.parent)
SITE_URL = os.environ.get('SITE_URL', 'https://USERNAME.github.io/REPO/')
D = json.loads(subprocess.check_output(['node', '-e', "const N=require(%s);console.log(JSON.stringify(N.derive(N.defaults())))" % json.dumps(SRC + '/params.js')], cwd=SRC))
TOK = re.compile(r'@([A-Z][A-Z0-9_]*)@')
E = html.escape

def tok(s, tag='span'):
    def r(m):
        k = m.group(1)
        if k not in D: raise KeyError('unknown token ' + k)
        return '<%s class="v" data-k="%s">%s</%s>' % (tag, k, E(D[k]), tag)
    return TOK.sub(r, s)
def T(s): return tok(E(s))
def plain(s): return TOK.sub(lambda m: D[m.group(1)], s)

# ---------- подсветка синтаксиса ----------
WORD = re.compile(r"'[^']*'|\"[^\"]*\"|\s+|[^\s'\"]+")
HD = re.compile(r"<<-?\s*'?([A-Za-z_]+)'?\s*$")
OPS = {'|', '&&', '||', ';', '>', '>>', '<<', '2>/dev/null', '>/dev/null'}
def seg(s, cls=None):
    e = tok(E(s))
    return '<span class="%s">%s</span>' % (cls, e) if cls else e
def hl_shell(line, cont):
    if line.lstrip().startswith('#'): return seg(line, 'c')
    out = []; first = not cont; parts = WORD.findall(line)
    for i, w in enumerate(parts):
        if w.isspace(): out.append(w); continue
        if w.startswith('#'): out.append(seg(''.join(parts[i:]), 'c')); break
        if w[0] in "'\"": out.append(seg(w, 's')); first = False
        elif w in OPS: out.append(seg(w, 'op')); first = w in ('|', '&&', '||', ';')
        elif first: out.append(seg(w, 'k')); first = w in ('for', 'while', 'if', 'sudo') and False
        elif w.startswith('-') and len(w) > 1: out.append(seg(w, 'o'))
        elif w.startswith('$'): out.append(seg(w, 'var'))
        else: out.append(seg(w))
        if (w.endswith(';') and w != ';') or w in ('do', 'then', 'else'): first = True
    return ''.join(out)
def hl_conf(line):
    s = line.strip()
    if not s: return ''
    if s.startswith(('#', '!', ';', '--')): return seg(line, 'c')
    m = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
    if m: return m.group(1) + seg(m.group(2), 'p') + '=' + seg(m.group(3), 's')
    m = re.match(r'^(.*?)(\s;.*)$', line)
    if m: return hl_conf(m.group(1)) + seg(m.group(2), 'c')
    m = re.match(r'^(\s*)(\S+)(.*)$', line)
    return m.group(1) + seg(m.group(2), 'p') + seg(m.group(3))
def hl(code):
    out = []; hd = None; cont = False
    for line in code.split('\n'):
        if hd:
            if line.strip() == hd: out.append(seg(line, 'h')); hd = None
            else: out.append(hl_conf(line))
            continue
        out.append(hl_shell(line, cont))
        m = HD.search(line)
        if m: hd = m.group(1)
        cont = line.rstrip().endswith('\\')
    return '\n'.join(out)

# ---------- шаблоны команд ----------
def eth(i, extra=''):
    x = ''.join('%s\\n' % e for e in extra.split()) if extra else ''
    return ("mkdir -p /etc/net/ifaces/%s\nprintf 'TYPE=eth\\nBOOTPROTO=static\\nDISABLED=no\\nCONFIG_IPV4=yes\\n%s' > /etc/net/ifaces/%s/options\n" % (i, x, i))
def trunk(p):
    return "mkdir -p /etc/net/ifaces/%s\nprintf 'TYPE=eth\\nBOOTPROTO=static\\nDISABLED=no\\n' > /etc/net/ifaces/%s/options\n" % (p, p)
def vlan(p, v, proto='static', extra=''):
    n = p + '.' + v
    return ("mkdir -p /etc/net/ifaces/%s\ncat > /etc/net/ifaces/%s/options << 'EOF'\nTYPE=vlan\nHOST=%s\nVID=%s\nBOOTPROTO=%s\nDISABLED=no\nCONFIG_IPV4=yes\n%sEOF\n" % (n, n, p, v, proto, extra))
MOD = "modprobe 8021q\ngrep -qx 8021q /etc/modules || echo 8021q >> /etc/modules\n"
FWD = "# IP-форвардинг\nsed -i 's/^net.ipv4.ip_forward.*/net.ipv4.ip_forward = 1/' /etc/net/sysctl.conf\nsysctl -w net.ipv4.ip_forward=1\n"
def nft(oif, pre=()):
    s = "cat > /etc/nftables/nftables.nft << 'EOF'\n#!/usr/sbin/nft -f\nflush ruleset\n\ntable ip nat {\n"
    if pre:
        s += "    chain prerouting {\n        type nat hook prerouting priority dstnat; policy accept;\n" + ''.join('        %s\n' % r for r in pre) + "    }\n\n"
    s += "    chain postrouting {\n        type nat hook postrouting priority srcnat; policy accept;\n        oifname \"%s\" masquerade\n    }\n}\nEOF\nsystemctl enable --now nftables\nsystemctl restart nftables\nnft list ruleset" % oif
    return s
def gre(local, remote, host, addr):
    return ("mkdir -p /etc/net/ifaces/gre1\ncat > /etc/net/ifaces/gre1/options << 'EOF'\nTYPE=iptun\nTUNTYPE=gre\nTUNLOCAL=%s\nTUNREMOTE=%s\nTUNTTL=255\nTUNOPTIONS='ttl 255'\nHOST=%s\nBOOTPROTO=static\nDISABLED=no\nCONFIG_IPV4=yes\nEOF\necho '%s' > /etc/net/ifaces/gre1/ipv4address\nsystemctl restart network\nip -br a show gre1" % (local, remote, host, addr))
def ospf(name, rid, nets):
    n = '\n'.join(' network %s area 0' % x for x in nets)
    return ("sed -i 's/^ospfd=no/ospfd=yes/' /etc/frr/daemons\n\ncat > /etc/frr/frr.conf << 'EOF'\nfrr defaults traditional\nhostname %s\nlog syslog informational\n!\ninterface gre1\n ip ospf network point-to-point\n ip ospf authentication message-digest\n ip ospf message-digest-key 1 md5 @PW@\n no ip ospf passive\nexit\n!\nrouter ospf\n ospf router-id %s\n passive-interface default\n%s\nexit\n!\nline vty\n!\nEOF\nsystemctl enable --now frr\nsystemctl restart frr" % (name, rid, n))

def B(devs, title, code, check=False, expect=None): return dict(devs=devs, title=title, code=code.strip('\n'), check=check, expect=expect)
def S(id, num, title, exam, desc, blocks): return dict(id=id, num=num, title=title, exam=exam, desc=desc, blocks=blocks)

MG = [('ISP', 'MG_ISP'), ('HQ-RTR', 'MG_HQRTR'), ('HQ-SRV', 'MG_HQSRV'), ('HQ-CLI', 'MG_HQCLI'), ('BR-RTR', 'MG_BRRTR'), ('BR-SRV', 'MG_BRSRV')]
SOA = "@   IN SOA @H_HQSRV@. root.@DOMAIN@. ( 2027010101 12H 1H 1W 1H )\n    IN NS  @H_HQSRV@."

M1 = [
 S('prep', '0', 'Подготовка стенда', 'вне КИМ',
   'Выполняется до заданий экзамена. Сеть управления вводится вручную в консоли VirtualBox, дальше подключайтесь с хоста по SSH (<code>ssh user@192.168.56.X</code>, затем <code>su -</code>) и вставляйте блоки целиком.',
   [B([d], 'Сеть управления @MG_IF@', eth('@MG_IF@', 'NM_CONTROLLED=no' if d == 'HQ-CLI' else '') + "echo '@%s_CIDR@' > /etc/net/ifaces/@MG_IF@/ipv4address\nsystemctl restart network" % k) for d, k in MG] + [
    B(['ISP'], 'Пакеты (пока работает NAT VirtualBox)', 'apt-get update && apt-get install -y nftables'),
    B(['HQ-RTR'], 'Пакеты', 'apt-get update && apt-get install -y frr nftables dhcp-server'),
    B(['BR-RTR'], 'Пакеты', 'apt-get update && apt-get install -y frr nftables'),
    B(['HQ-SRV'], 'Пакеты', 'apt-get update && apt-get install -y bind bind-utils openssh-server'),
    B(['BR-SRV'], 'Пакеты', 'apt-get update && apt-get install -y openssh-server'),
    B(['HQ-CLI'], 'Пакеты', 'apt-get update && apt-get install -y dhcpcd bind-utils'),
    B(['HQ-RTR', 'BR-RTR', 'HQ-SRV', 'BR-SRV', 'HQ-CLI'], 'Отключить NAT-адаптер @ISP_WAN@ (все, кроме ISP)',
      "# дальше интернет идёт только через ISP\nmkdir -p /etc/net/ifaces/@ISP_WAN@\nprintf 'TYPE=eth\\nDISABLED=yes\\nONBOOT=no\\n' > /etc/net/ifaces/@ISP_WAN@/options\nip addr flush dev @ISP_WAN@\nip link set @ISP_WAN@ down\nsystemctl restart network\nip route"),
    B(['Все ВМ'], 'Клонированные ВМ: новые ключи SSH и machine-id', """# у клонов одинаковые ключи хоста — ssh предупреждает о подмене, эксперт видит один отпечаток
rm -f /etc/openssh/ssh_host_*
ssh-keygen -A
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
systemctl restart sshd 2>/dev/null
ssh-keygen -lf /etc/openssh/ssh_host_ed25519_key.pub""", expect='отпечаток ED25519 на каждой ВМ свой'),
   ]),
 S('t1', '1', 'Базовая настройка устройств', 'Задание 1',
   'Имена (FQDN), адресация внешних интерфейсов и сегмента BR, IP-форвардинг на маршрутизаторах. Адреса сегмента HQ задаются в задании 4 (VLAN).',
   [B(['ISP'], 'Имя', 'hostnamectl set-hostname @H_ISP@; exec bash'),
    B(['HQ-RTR'], 'Имя, интерфейс к ISP, форвардинг', 'hostnamectl set-hostname @H_HQRTR@\n\n' + eth('@HQ_WAN_IF@') + "echo '@HQ_WAN_CIDR@' > /etc/net/ifaces/@HQ_WAN_IF@/ipv4address\necho 'default via @ISP_HQ_IP@' > /etc/net/ifaces/@HQ_WAN_IF@/ipv4route\n\n" + FWD + 'systemctl restart network; exec bash'),
    B(['BR-RTR'], 'Имя, интерфейс к ISP, VLAN в сторону BR-SRV, форвардинг', 'hostnamectl set-hostname @H_BRRTR@\n\n' + eth('@BR_WAN_IF@') + "echo '@BR_WAN_CIDR@' > /etc/net/ifaces/@BR_WAN_IF@/ipv4address\necho 'default via @ISP_BR_IP@' > /etc/net/ifaces/@BR_WAN_IF@/ipv4route\n\n# trunk @BR_LAN_IF@ (lab-core-br): VLAN @V_SRV@ и @V_MGMT@\n" + MOD + trunk('@BR_LAN_IF@') + vlan('@BR_LAN_IF@', '@V_SRV@') + vlan('@BR_LAN_IF@', '@V_MGMT@') + "echo '@BR_GW_SRV@' > /etc/net/ifaces/@BR_LAN_IF@.@V_SRV@/ipv4address\necho '@BR_GW_MGMT@' > /etc/net/ifaces/@BR_LAN_IF@.@V_MGMT@/ipv4address\n\n" + FWD + 'systemctl restart network; exec bash\nip -br a'),
    B(['BR-SRV'], 'Имя и адрес в VLAN @V_SRV@', 'hostnamectl set-hostname @H_BRSRV@\n\n' + MOD + trunk('@BR_SRV_IF@') + vlan('@BR_SRV_IF@', '@V_SRV@') + "echo '@BR_SRV_CIDR@' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/ipv4address\necho 'default via @BR_GW_SRV_IP@' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/ipv4route\nsystemctl restart network; exec bash\nip -br a"),
    B(['HQ-SRV'], 'Имя', 'hostnamectl set-hostname @H_HQSRV@; exec bash'),
    B(['HQ-CLI'], 'Имя', 'hostnamectl set-hostname @H_HQCLI@; exec bash'),
   ]),
 S('t2', '2', 'Доступ в Интернет на ISP', 'Задание 2',
   'Внешний интерфейс получает адрес по DHCP от NAT VirtualBox (маршрут по умолчанию и DNS приходят оттуда же). Для HQ-RTR и BR-RTR — динамическая трансляция (masquerade).',
   [B(['ISP'], 'Интерфейсы и форвардинг', "mkdir -p /etc/net/ifaces/@ISP_WAN@\nprintf 'TYPE=eth\\nBOOTPROTO=dhcp\\nDISABLED=no\\nCONFIG_IPV4=yes\\n' > /etc/net/ifaces/@ISP_WAN@/options\n\n" + eth('@ISP_HQ_IF@') + "echo '@ISP_HQ@' > /etc/net/ifaces/@ISP_HQ_IF@/ipv4address\n\n" + eth('@ISP_BR_IF@') + "echo '@ISP_BR@' > /etc/net/ifaces/@ISP_BR_IF@/ipv4address\n\n" + FWD + 'systemctl restart network\nip -br a'),
    B(['ISP'], 'NAT в сторону Интернета', nft('@ISP_WAN@')),
   ]),
 S('t3', '3', 'Локальные учётные записи', 'Задание 3',
   'sshuser на серверах, net_admin на маршрутизаторах, sudo без пароля.',
   [B(['HQ-SRV', 'BR-SRV'], 'Пользователь sshuser', "id sshuser >/dev/null 2>&1 || useradd -m -u @SSH_UID@ sshuser\necho 'sshuser:@PW@' | chpasswd\nusermod -aG wheel sshuser\ngrep -q '^sshuser ' /etc/sudoers || echo 'sshuser ALL=(ALL:ALL) NOPASSWD: ALL' >> /etc/sudoers\nvisudo -c\nid sshuser"),
    B(['HQ-RTR', 'BR-RTR'], 'Пользователь net_admin', "id net_admin >/dev/null 2>&1 || useradd -m net_admin\necho 'net_admin:@PW@' | chpasswd\nusermod -aG wheel net_admin\ngrep -q '^net_admin ' /etc/sudoers || echo 'net_admin ALL=(ALL:ALL) NOPASSWD: ALL' >> /etc/sudoers\nvisudo -c\nid net_admin"),
    B(['HQ-SRV', 'BR-SRV', 'HQ-RTR', 'BR-RTR'], 'Проверка', "for u in sshuser net_admin; do id $u 2>/dev/null && sudo -l -U $u | tail -1; done\nls -l /etc/sudoers.d/", check=True,
      expect='серверы: uid=@SSH_UID@(sshuser), роутеры: net_admin; (ALL : ALL) NOPASSWD: ALL; файлы в sudoers.d — права 0400 (r--------), иначе visudo ругается'),
   ]),
 S('t4', '4', 'Коммутация в сегменте HQ (VLAN)', 'Задание 4',
   'Router-on-a-stick: все VLAN маршрутизируются через один адаптер HQ-RTR (внутренняя сеть lab-core). HQ-SRV и HQ-CLI тегируют трафик сами.',
   [B(['HQ-RTR'], 'Trunk + VLAN @V_SRV@ / @V_CLI@ / @V_MGMT@', MOD + trunk('@HQ_LAN_IF@') + vlan('@HQ_LAN_IF@', '@V_SRV@') + vlan('@HQ_LAN_IF@', '@V_CLI@') + vlan('@HQ_LAN_IF@', '@V_MGMT@') + "echo '@HQ_GW_SRV@'  > /etc/net/ifaces/@HQ_LAN_IF@.@V_SRV@/ipv4address\necho '@HQ_GW_CLI@'  > /etc/net/ifaces/@HQ_LAN_IF@.@V_CLI@/ipv4address\necho '@HQ_GW_MGMT@' > /etc/net/ifaces/@HQ_LAN_IF@.@V_MGMT@/ipv4address\nsystemctl restart network\nip -br a"),
    B(['HQ-SRV'], 'VLAN @V_SRV@', MOD + trunk('@HQ_SRV_IF@') + vlan('@HQ_SRV_IF@', '@V_SRV@') + "echo '@HQ_SRV_CIDR@' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/ipv4address\necho 'default via @HQ_GW_SRV_IP@' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/ipv4route\nsystemctl restart network\nping -c3 @HQ_GW_SRV_IP@"),
    B(['HQ-CLI'], 'VLAN @V_CLI@ (статикой, до задания 9)', MOD + trunk('@HQ_CLI_IF@') + vlan('@HQ_CLI_IF@', '@V_CLI@', 'static', 'NM_CONTROLLED=no\n') + "echo '@HQ_CLI_CIDR@' > /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4address\necho 'default via @HQ_GW_CLI_IP@' > /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4route\nsystemctl restart network\nping -c3 @HQ_GW_CLI_IP@"),
   ]),
 S('t5', '5', 'Безопасный удалённый доступ (SSH)', 'Задание 5',
   'Порт, только sshuser, 2 попытки входа, баннер. После этого на серверы заходите так: <code>ssh -p @SSH_PORT@ sshuser@&lt;адрес&gt;</code>, затем <code>sudo -i</code>.',
   [B(['HQ-SRV', 'BR-SRV'], 'Настройка sshd', "cp -n /etc/openssh/sshd_config /etc/openssh/sshd_config.bak\n# баннер — дословно как в КИМ, одинаковый на всех ВМ\necho '@BANNER@' > /etc/openssh/banner\n\nsed -i -E \\\n  -e 's/^#?Port .*/Port @SSH_PORT@/' \\\n  -e 's/^#?MaxAuthTries .*/MaxAuthTries 2/' \\\n  -e 's|^#?Banner .*|Banner /etc/openssh/banner|' \\\n  /etc/openssh/sshd_config\ngrep -q '^AllowUsers' /etc/openssh/sshd_config || echo 'AllowUsers sshuser' >> /etc/openssh/sshd_config\n\nsshd -t && systemctl enable sshd && systemctl restart sshd\ndiff /etc/openssh/sshd_config.bak /etc/openssh/sshd_config\ngrep -E '^(Port|MaxAuthTries|Banner|AllowUsers)' /etc/openssh/sshd_config"),
    B(['HQ-CLI'], 'Проверка', 'ssh -p @SSH_PORT@ sshuser@@HQ_SRV_IP@\nssh -p @SSH_PORT@ sshuser@@BR_SRV_IP@   # после заданий 6–7\nssh -p @SSH_PORT@ root@@HQ_SRV_IP@      # должен быть отказ', check=True,
      expect='перед паролем — «@BANNER@»; вход sshuser — есть; root — Permission denied'),
   ]),
 S('t6', '6', 'IP-туннель GRE', 'Задание 6', 'Минимальная маска для двух адресов туннеля — /30.',
   [B(['HQ-RTR'], 'gre1 → BR-RTR', gre('@HQ_WAN_IP@', '@BR_WAN_IP@', '@HQ_WAN_IF@', '@GRE_HQ@')),
    B(['BR-RTR'], 'gre1 → HQ-RTR', gre('@BR_WAN_IP@', '@HQ_WAN_IP@', '@BR_WAN_IF@', '@GRE_BR_CIDR@')),
    B(['HQ-RTR'], 'Проверка', 'ping -c3 @GRE_BR@', check=True, expect='3 packets transmitted, 3 received, 0% packet loss'),
   ]),
 S('t7', '7', 'Динамическая маршрутизация OSPF', 'Задание 7',
   'FRR, area 0. Все интерфейсы пассивны, OSPF работает только на gre1. Аутентификация MD5.',
   [B(['HQ-RTR'], 'FRR / ospfd', ospf('@H_HQRTR@', '@GRE_HQ_IP@', ['@HQ_GW_SRV_SUBNET@', '@HQ_GW_CLI_SUBNET@', '@HQ_GW_MGMT_SUBNET@', '@GRE_HQ_SUBNET@'])),
    B(['BR-RTR'], 'FRR / ospfd', ospf('@H_BRRTR@', '@GRE_BR@', ['@BR_GW_SRV_SUBNET@', '@BR_GW_MGMT_SUBNET@', '@GRE_HQ_SUBNET@'])),
    B(['HQ-RTR', 'BR-RTR'], 'Проверка: сосед в состоянии Full', "vtysh -c 'show ip ospf neighbor'\nvtysh -c 'show ip route ospf'", check=True, expect='сосед в состоянии Full/-, интерфейс gre1; маршруты O>* до сетей другого офиса'),
   ]),
 S('t8', '8', 'Динамическая трансляция адресов (NAT)', 'Задание 8',
   'Masquerade в сторону ISP. Трафик между офисами идёт через gre1 и не транслируется.',
   [B(['HQ-RTR'], 'NAT → ISP (@HQ_WAN_IF@)', nft('@HQ_WAN_IF@')),
    B(['BR-RTR'], 'NAT → ISP (@BR_WAN_IF@)', nft('@BR_WAN_IF@')),
    B(['HQ-SRV', 'BR-SRV'], 'Проверка', 'ping -c3 77.88.8.8', check=True, expect='0% packet loss'),
   ]),
 S('t9', '9', 'DHCP для HQ-CLI', 'Задание 9',
   'Сервер — HQ-RTR, только на VLAN клиентов. Адрес маршрутизатора исключён из пула; HQ-CLI получает зарезервированный адрес по MAC.',
   [B(['HQ-RTR'], 'dhcpd', """cat > /etc/dhcp/dhcpd.conf << 'EOF'
option domain-name "@DOMAIN@";
option domain-name-servers @HQ_SRV_IP@;
default-lease-time 600;
max-lease-time 7200;
authoritative;

subnet @HQ_GW_CLI_NET@ netmask @HQ_GW_CLI_MASK@ {
    range @DHCP_FROM@ @DHCP_TO@;
    option routers @HQ_GW_CLI_IP@;
}

# MAC HQ-CLI: ip link show @HQ_CLI_IF@
host hq-cli {
    hardware ethernet @HQ_CLI_MAC@;
    fixed-address @HQ_CLI_IP@;
}
EOF
dhcpd -t -cf /etc/dhcp/dhcpd.conf

mkdir -p /etc/systemd/system/dhcpd.service.d
cat > /etc/systemd/system/dhcpd.service.d/override.conf << 'EOF'
[Service]
ExecStart=
ExecStart=/usr/sbin/dhcpd -f -q -cf /etc/dhcp/dhcpd.conf @HQ_LAN_IF@.@V_CLI@
EOF
systemctl daemon-reload
systemctl enable --now dhcpd
systemctl restart dhcpd
systemctl status dhcpd --no-pager"""),
    B(['HQ-CLI'], 'Перевести VLAN @V_CLI@ на DHCP', vlan('@HQ_CLI_IF@', '@V_CLI@', 'dhcp', 'NM_CONTROLLED=no\n') + "rm -f /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4address /etc/net/ifaces/@HQ_CLI_IF@.@V_CLI@/ipv4route\nsystemctl restart network\nip -br a show @HQ_CLI_IF@.@V_CLI@\ncat /etc/resolv.conf"),
    B(['HQ-CLI'], 'Проверка', "ip -br a show @HQ_CLI_IF@.@V_CLI@\nip route | grep default\ngrep nameserver /etc/resolv.conf", check=True,
      expect='@HQ_CLI_IP@ (резерв по MAC), default via @HQ_GW_CLI_IP@, один nameserver @HQ_SRV_IP@ — без посторонних DNS вроде 1.1.1.1'),
   ]),
 S('t10', '10', 'DNS (BIND на HQ-SRV)', 'Задание 10',
   'Зона и обратные зоны по таблице 3 КИМ. BIND работает в chroot <code>/var/lib/bind</code>, поэтому путь <code>/zone</code> = <code>/var/lib/bind/zone</code>.',
   [B(['HQ-SRV'], 'options.conf и зоны', """cat > /etc/bind/options.conf << 'EOF'
options {
    directory "/zone";
    pid-file none;
    listen-on { 127.0.0.1; @HQ_SRV_IP@; };
    listen-on-v6 { none; };
    allow-query { any; };
    recursion yes;
    allow-recursion { any; };
    forwarders { @DNS_FWD@; };
    forward first;
    dnssec-validation no;
};
EOF

grep -q '"@DOMAIN@"' /etc/bind/local.conf || cat >> /etc/bind/local.conf << 'EOF'
zone "@DOMAIN@" {
    type master;
    file "/zone/@DOMAIN@.zone";
};
zone "@REV_HQ@" {
    type master;
    file "/zone/@REV_HQ_FILE@";
};
zone "@REV_BR@" {
    type master;
    file "/zone/@REV_BR_FILE@";
};
EOF
named-checkconf"""),
    B(['HQ-SRV'], 'Файлы зон', """mkdir -p /var/lib/bind/zone
cat > /var/lib/bind/zone/@DOMAIN@.zone << 'EOF'
$TTL 1D
@       IN SOA  @H_HQSRV@. root.@DOMAIN@. (
                2027010101 ; serial
                12H        ; refresh
                1H         ; retry
                1W         ; expire
                1H )       ; minimum
        IN NS   @H_HQSRV@.
hq-rtr  IN A    @HQ_GW_MGMT_IP@
br-rtr  IN A    @BR_GW_MGMT_IP@
br-fw   IN A    @BR_FW_IP@
hq-srv  IN A    @HQ_SRV_IP@
hq-cli  IN A    @HQ_CLI_IP@
br-srv  IN A    @BR_SRV_IP@
docker  IN A    @ISP_HQ_IP@
web     IN A    @ISP_BR_IP@
EOF

cat > /var/lib/bind/zone/@REV_HQ_FILE@ << 'EOF'
$TTL 1D
""" + SOA + """
@REV_HQ_PTR@  IN PTR @H_HQSRV@.
EOF

cat > /var/lib/bind/zone/@REV_BR_FILE@ << 'EOF'
$TTL 1D
""" + SOA + """
@REV_BR_PTR@  IN PTR @H_BRSRV@.
EOF

chown named:named /var/lib/bind/zone/*
chmod 640 /var/lib/bind/zone/*
named-checkzone @DOMAIN@ /var/lib/bind/zone/@DOMAIN@.zone
named-checkzone @REV_HQ@ /var/lib/bind/zone/@REV_HQ_FILE@
named-checkzone @REV_BR@ /var/lib/bind/zone/@REV_BR_FILE@"""),
    B(['HQ-SRV'], 'Запуск и локальный резолвер', """sed -i 's|^#\\?CHROOT=.*|CHROOT="-t /var/lib/bind"|' /etc/sysconfig/bind
grep CHROOT /etc/sysconfig/bind
systemctl enable --now bind
systemctl restart bind

printf 'search @DOMAIN@\\nnameserver 127.0.0.1\\n' > /etc/net/ifaces/@HQ_SRV_IF@.@V_SRV@/resolv.conf
systemctl restart network"""),
    B(['HQ-SRV', 'HQ-CLI'], 'Проверка', 'dig @@HQ_SRV_IP@ @H_HQRTR@ +short\ndig @@HQ_SRV_IP@ @H_BRSRV@ +short\ndig @@HQ_SRV_IP@ -x @HQ_SRV_IP@ +short\ndig @@HQ_SRV_IP@ -x @BR_SRV_IP@ +short\ndig @@HQ_SRV_IP@ ya.ru +short', check=True, expect='@HQ_GW_MGMT_IP@, @BR_SRV_IP@, @H_HQSRV@., @H_BRSRV@., адреса ya.ru'),
   ]),
 S('t11', '11', 'Часовой пояс', 'Задание 11', 'На всех устройствах — по месту проведения экзамена.',
   [B(['Все ВМ'], 'Часовой пояс', 'timedatectl set-timezone @TZ@\ntimedatectl')]),
 S('check', '✓', 'Итоговая проверка', 'вне КИМ', 'Быстрый прогон перед сдачей.',
   [B(['HQ-CLI'], 'Связность, DNS, SSH', 'ip -br a\nip route\nping -c2 @HQ_GW_CLI_IP@\nping -c2 @HQ_SRV_IP@\nping -c2 @BR_SRV_IP@\nping -c2 77.88.8.8\nhost @H_HQSRV@\nhost ya.ru\nssh -p @SSH_PORT@ sshuser@@H_HQSRV@', check=True),
    B(['HQ-RTR', 'BR-RTR'], 'Маршрутизация и NAT', "ip -br a\nvtysh -c 'show ip ospf neighbor'\nvtysh -c 'show ip route'\nnft list ruleset\nsystemctl is-active frr nftables", check=True),
    B(['Все ВМ'], 'Один маршрут по умолчанию', "ip route | grep '^default'\nip route | grep -c '^default'", check=True,
      expect='ровно 1; два default (через @MG_IF@ и через офис) — типовая потеря баллов'),
   ]),
]

ISO = "mkdir -p @ISO_DIR@\n# содержимое Additional.iso; если каталог пуст — монтируем диск\n[ -n \"$(ls -A @ISO_DIR@ 2>/dev/null)\" ] || mount @ISO_DEV@ @ISO_DIR@\n"
def chrony_client(ip):
    return "apt-get install -y chrony\nsed -i -E '/^(pool|server) /d' /etc/chrony.conf\necho 'server %s iburst' >> /etc/chrony.conf\nsystemctl enable --now chronyd\nsystemctl restart chronyd\nchronyc sources" % ip
M2 = [
 S('m2t1', '1', 'Контроллер домена Samba DC', 'Задание 1',
   'Домен поднимается на BR-SRV с внутренним DNS Samba. HQ-CLI по-прежнему использует DNS HQ-SRV, поэтому на HQ-SRV добавляются SRV-записи, указывающие на контроллер. HQ-CLI вводится в домен через winbind; входить могут только члены группы <code>hq</code>, домашний каталог создаётся автоматически. Kerberos чувствителен ко времени: при ошибке <code>Clock skew</code> сначала выполните задание 4.',
   [B(['BR-SRV'], 'Установка и развёртывание домена', """apt-get update && apt-get install -y task-samba-dc
grep -q '@H_BRSRV@' /etc/hosts || echo '@BR_SRV_IP@ @H_BRSRV@ br-srv' >> /etc/hosts
rm -f /etc/samba/smb.conf
rm -rf /var/lib/samba /var/cache/samba
mkdir -p /var/lib/samba/sysvol
samba-tool domain provision --realm=@REALM@ --domain=@WG@ \\
  --server-role=dc --dns-backend=SAMBA_INTERNAL \\
  --adminpass='@PW@' --option='dns forwarder = @HQ_SRV_IP@'
cp -f /var/lib/samba/private/krb5.conf /etc/krb5.conf
systemctl enable --now samba
printf 'search @DOMAIN@\\nnameserver 127.0.0.1\\n' > /etc/net/ifaces/@BR_SRV_IF@.@V_SRV@/resolv.conf
systemctl restart network
samba-tool domain info 127.0.0.1
# внешние имена должны резолвиться через пересылку на HQ-SRV
host ya.ru 127.0.0.1"""),
    B(['BR-SRV'], 'Политика паролей, пользователи и группа hq', """samba-tool domain passwordsettings set --min-pwd-length=8 \\
  --account-lockout-threshold=5 --account-lockout-duration=30 \\
  --reset-account-lockout-after=30
samba-tool group add hq 2>/dev/null || true
for i in $(seq 1 @HQ_USERS@); do
  # пароль: @HQ_USER_PW@1, @HQ_USER_PW@2, …
  samba-tool user add hquser$i '@HQ_USER_PW@'"$i"
  samba-tool group addmembers hq hquser$i
done
samba-tool group listmembers hq
samba-tool domain passwordsettings show""",
      expect="hquser1 … hquser@HQ_USERS@ в списке группы hq; Minimum password length: 8"),
    B(['HQ-SRV'], 'SRV-записи контроллера в BIND', """if ! grep -q '^_ldap._tcp ' /var/lib/bind/zone/@DOMAIN@.zone; then
cat >> /var/lib/bind/zone/@DOMAIN@.zone << 'EOF'
_ldap._tcp               IN SRV 0 100 389  @H_BRSRV@.
_ldap._tcp.dc._msdcs     IN SRV 0 100 389  @H_BRSRV@.
_kerberos._tcp           IN SRV 0 100 88   @H_BRSRV@.
_kerberos._udp           IN SRV 0 100 88   @H_BRSRV@.
_kerberos._tcp.dc._msdcs IN SRV 0 100 88   @H_BRSRV@.
_kpasswd._tcp            IN SRV 0 100 464  @H_BRSRV@.
_kpasswd._udp            IN SRV 0 100 464  @H_BRSRV@.
_gc._tcp                 IN SRV 0 100 3268 @H_BRSRV@.
EOF
sed -i 's/2027010101 ; serial/2027010102 ; serial/' /var/lib/bind/zone/@DOMAIN@.zone
fi
named-checkzone @DOMAIN@ /var/lib/bind/zone/@DOMAIN@.zone
systemctl restart bind
dig @127.0.0.1 _ldap._tcp.@DOMAIN@ SRV +short""", expect="0 100 389 @H_BRSRV@."),
    B(['HQ-CLI'], 'Ввод в домен (winbind)', """apt-get update && apt-get install -y task-auth-ad-winbind
host -t SRV _ldap._tcp.@DOMAIN@
system-auth write ad @DOMAIN@ hq-cli @WG@ 'administrator' '@PW@'
reboot
# после перезагрузки:
# net ads testjoin && wbinfo -u | head"""),
    B(['HQ-CLI'], 'Вход только для группы hq, sudo: cat, grep, id', """# SID группы надёжнее имени
SID=$(wbinfo --name-to-sid hq | awk '{print $1}')
echo "$SID"
cp -a /etc/security/pam_winbind.conf /etc/security/pam_winbind.conf.bak 2>/dev/null
cat > /etc/security/pam_winbind.conf << EOF
[global]
require_membership_of = $SID
mkhomedir = yes
krb5_auth = yes
krb5_ccache_type = FILE
cached_login = yes
EOF
mkdir -p /home/@REALM@ && chmod 755 /home/@REALM@
grep -q 'winbind offline logon' /etc/samba/smb.conf || sed -i '/^\\[global\\]/a winbind offline logon = yes' /etc/samba/smb.conf
testparm -s >/dev/null && systemctl restart winbind

# режим wheelonly запрещает запуск sudo всем, кроме wheel
control sudo public
echo '%hq ALL=(ALL) NOPASSWD: /bin/cat, /bin/grep, /usr/bin/id' > /etc/sudoers.d/hq
chmod 400 /etc/sudoers.d/hq
visudo -c"""),
    B(['HQ-CLI'], 'Проверка', """wbinfo --name-to-sid hq
id hquser1
sudo -l -U hquser1
# войдите hquser1 / @HQ_USER_PW@1 через экран входа, затем в терминале:
# pwd; sudo cat /etc/hostname; sudo vi /etc/hosts""", check=True,
      expect="pwd → /home/@REALM@/hquser1 (создан автоматически)\nsudo cat — работает; sudo vi — «is not allowed to execute»\nпользователь не из hq — Authentication failure"),
   ]),
 S('m2t2', '2', 'Файловое хранилище RAID 0', 'Задание 2',
   'Массив md0 из двух дополнительных дисков, ext4 прямо на массиве, монтирование в <code>/raid</code> по UUID с <code>nofail</code> (система загрузится даже без массива). Имена дисков проверьте по <code>lsblk</code>.',
   [B(['HQ-SRV'], 'mdadm, файловая система, fstab', """apt-get install -y mdadm
lsblk
mdadm --zero-superblock --force @RAID_D1@ @RAID_D2@ 2>/dev/null
mdadm --create /dev/md0 --level=0 --raid-devices=2 @RAID_D1@ @RAID_D2@ --run
mkfs.ext4 -F /dev/md0
grep -q '^ARRAY /dev/md0' /etc/mdadm.conf || mdadm --detail --scan >> /etc/mdadm.conf
mkdir -p /raid
grep -q ' /raid ' /etc/fstab || printf 'UUID=%s /raid ext4 defaults,nofail 0 0\\n' "$(blkid -s UUID -o value /dev/md0)" >> /etc/fstab
systemctl daemon-reload && mount -a
cat /proc/mdstat
df -h /raid"""),
    B(['HQ-SRV'], 'Проверка после перезагрузки', "cat /proc/mdstat\ndf -h /raid\ngrep -E 'md0|/raid' /etc/mdadm.conf /etc/fstab", check=True,
      expect="md0 : active raid0 …; /dev/md0 смонтирован в /raid (≈ сумма дисков)"),
   ]),
 S('m2t3', '3', 'Сервер NFS', 'Задание 3',
   'Каталог <code>/raid/nfs</code> с доступом на чтение и запись только для сети HQ-CLI; на клиенте — автомонтирование в <code>/mnt/nfs</code> (<code>_netdev,x-systemd.automount</code>).',
   [B(['HQ-SRV'], 'Экспорт /raid/nfs', """apt-get install -y nfs-server nfs-utils
mkdir -p /raid/nfs
chmod 777 /raid/nfs
grep -q '^/raid/nfs ' /etc/exports || echo '/raid/nfs @HQ_GW_CLI_SUBNET@(rw,sync,no_subtree_check)' >> /etc/exports
systemctl enable --now nfs-server
exportfs -rav
showmount -e localhost"""),
    B(['HQ-CLI'], 'Автомонтирование', """apt-get install -y nfs-clients nfs-utils
showmount -e @HQ_SRV_IP@
mkdir -p /mnt/nfs
grep -q ' /mnt/nfs ' /etc/fstab || echo '@HQ_SRV_IP@:/raid/nfs /mnt/nfs nfs defaults,_netdev,x-systemd.automount 0 0' >> /etc/fstab
systemctl daemon-reload && mount -a
touch /mnt/nfs/probe && ls -l /mnt/nfs"""),
    B(['HQ-SRV'], 'Проверка', 'ls -l /raid/nfs\nexportfs -v', check=True,
      expect="файл probe, созданный на HQ-CLI; /raid/nfs  @HQ_GW_CLI_SUBNET@(rw,…)"),
   ]),
 S('m2t4', '4', 'Служба времени chrony', 'Задание 4',
   'ISP — сервер stratum 5 (<code>minstratum 4</code> у вышестоящего источника даёт ровно 5, <code>local stratum 5</code> — на случай пропажи Интернета). Клиенты обращаются к ближайшему адресу ISP, запросы проходят через NAT маршрутизаторов.',
   [B(['ISP'], 'NTP-сервер', """apt-get install -y chrony
cat > /etc/chrony.conf << 'EOF'
server @NTP_UP@ iburst minstratum 4
local stratum 5
allow @ISP_HQ_SUBNET@
allow @ISP_BR_SUBNET@
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
EOF
systemctl enable --now chronyd
systemctl restart chronyd
chronyc tracking | grep -i stratum""", expect="Stratum         : 5"),
    B(['HQ-RTR', 'HQ-SRV', 'HQ-CLI'], 'Клиент (офис HQ)', chrony_client('@ISP_HQ_IP@')),
    B(['BR-RTR', 'BR-SRV'], 'Клиент (офис BR)', chrony_client('@ISP_BR_IP@')),
    B(['ISP'], 'Проверка: клиенты видны на ISP', 'chronyc clients\nchronyc tracking | grep -i stratum', check=True,
      expect="в списке @HQ_WAN_IP@ и @BR_WAN_IP@ (клиенты за NAT); на клиентах chronyc sources — ^* @ISP_HQ_IP@ / @ISP_BR_IP@"),
   ]),
 S('m2t5', '5', 'Ansible на BR-SRV', 'Задание 5',
   'Ключи раскладываются <code>ssh-copy-id</code> по паролю, после этого <code>ansible all -m ping</code> отвечает pong без предупреждений. Порт SSH: HQ-SRV — @SSH_PORT@, HQ-CLI и маршрутизаторы — @ANS_PORT@.',
   [B(['HQ-CLI'], 'sshd и пользователь для Ansible', "apt-get install -y openssh-server python3\nid sshuser >/dev/null 2>&1 || useradd -m sshuser\necho 'sshuser:@PW@' | chpasswd\nsystemctl enable --now sshd"),
    B(['HQ-SRV', 'HQ-RTR', 'BR-RTR'], 'Python на управляемых машинах', 'apt-get install -y python3'),
    B(['BR-SRV'], 'Ключи SSH', """apt-get install -y ansible openssh-clients
[ -f /root/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519
# MaxAuthTries 2: при «Too many authentication failures» помогает PreferredAuthentications=password
O='-o StrictHostKeyChecking=accept-new -o PreferredAuthentications=password'
ssh-copy-id $O -p @SSH_PORT@ sshuser@@HQ_SRV_IP@
ssh-copy-id $O -p @ANS_PORT@ sshuser@@HQ_CLI_IP@
ssh-copy-id $O -p @ANS_PORT@ net_admin@@HQ_GW_MGMT_IP@
ssh-copy-id $O -p @ANS_PORT@ net_admin@@BR_GW_MGMT_IP@"""),
    B(['BR-SRV'], 'Инвентарь и конфигурация', """mkdir -p /etc/ansible
cat > /etc/ansible/hosts << 'EOF'
[hq]
hq-srv ansible_host=@HQ_SRV_IP@ ansible_port=@SSH_PORT@ ansible_user=sshuser
hq-cli ansible_host=@HQ_CLI_IP@ ansible_port=@ANS_PORT@ ansible_user=sshuser
hq-rtr ansible_host=@HQ_GW_MGMT_IP@ ansible_port=@ANS_PORT@ ansible_user=net_admin

[br]
br-rtr ansible_host=@BR_GW_MGMT_IP@ ansible_port=@ANS_PORT@ ansible_user=net_admin

[all:vars]
ansible_python_interpreter=/usr/bin/python3
EOF
cat > /etc/ansible/ansible.cfg << 'EOF'
[defaults]
inventory = /etc/ansible/hosts
host_key_checking = False
deprecation_warnings = False
interpreter_python = /usr/bin/python3
EOF
cd /etc/ansible && ansible all -m ping"""),
    B(['BR-SRV'], 'Проверка', 'ansible all -m ping', check=True,
      expect='4 × SUCCESS … "ping": "pong", без WARNING'),
   ]),
 S('m2t6', '6', 'Веб-приложение в Docker', 'Задание 6',
   'Образы (<code>*.tar</code>) и compose.yaml берутся с Additional.iso (<code>@ISO_DIR@</code>). Без <code>container_name</code> контейнеры получат имена вида <code>testapp-testapp-1</code> — проверяющему нужны <code>testapp</code> и <code>db</code>.',
   [B(['BR-SRV'], 'Docker и стек testapp', "apt-get install -y docker-engine docker-compose-v2\nsystemctl enable --now docker\n" + ISO + """ls @ISO_DIR@ @ISO_DIR@/docker
for f in @ISO_DIR@/docker/*.tar; do docker load -i "$f"; done
docker images
cat @ISO_DIR@/docker/readme.txt
mkdir -p /root/testapp
cp @ISO_DIR@/compose.yaml /root/testapp/ 2>/dev/null || cp @ISO_DIR@/docker/compose.yaml /root/testapp/
cd /root/testapp
# имена контейнеров testapp и db (сервисы с отступом в 2 пробела)
grep -q container_name compose.yaml || sed -i -E 's/^  (testapp|db):[[:space:]]*$/&\\n    container_name: \\1/' compose.yaml
grep -nE 'image|container_name|ports|restart|- "' compose.yaml
docker compose config -q && docker compose up -d
docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'"""),
    B(['BR-SRV'], 'Проверка', "docker ps --format '{{.Names}} {{.Status}}'\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_SRV_IP@:@APP_PORT@", check=True,
      expect="testapp Up …, db Up …; код 200"),
   ]),
 S('m2t7', '7', 'Веб-приложение на Apache', 'Задание 7',
   'Apache + PHP + MariaDB на HQ-SRV. В <code>dump.sql</code> нет <code>CREATE DATABASE</code>, поэтому базу создают заранее; параметры подключения в <code>index.php</code> — переменные <code>$username</code>, <code>$password</code>, <code>$dbname</code>.',
   [B(['HQ-SRV'], 'LAMP и база webdb', "apt-get install -y lamp-server\nphp -m | grep -i mysqli\n" + ISO + """ls @ISO_DIR@/web
systemctl enable --now mysqld
mariadb << 'EOF'
CREATE DATABASE IF NOT EXISTS webdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'web'@'localhost' IDENTIFIED BY '@PW@';
GRANT ALL PRIVILEGES ON webdb.* TO 'web'@'localhost';
FLUSH PRIVILEGES;
EOF
mariadb webdb < @ISO_DIR@/web/dump.sql
mariadb -u web -p'@PW@' -e 'SHOW TABLES' webdb"""),
    B(['HQ-SRV'], 'Файлы сайта и запуск', """rm -f /var/www/html/index.html
cp @ISO_DIR@/web/index.php @ISO_DIR@/web/logo.png /var/www/html/
sed -i -E \\
  -e 's/^(\\$username *= *)"[^"]*"/\\1"web"/' \\
  -e 's/^(\\$password *= *)"[^"]*"/\\1"@PW@"/' \\
  -e 's/^(\\$dbname *= *)"[^"]*"/\\1"webdb"/' \\
  /var/www/html/index.php
sed -n '2,7p' /var/www/html/index.php
systemctl enable --now httpd2
systemctl restart httpd2
curl -s http://127.0.0.1:@WEB_PORT@/ | head -20"""),
    B(['HQ-SRV'], 'Проверка после перезагрузки', "systemctl is-active mysqld httpd2\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_SRV_IP@:@WEB_PORT@/", check=True,
      expect="active, active; код 200, в HTML — строки таблицы из dump.sql"),
    B(['HQ-SRV'], 'Если MariaDB не запускается (ibdata1 повреждён)', """# симптом в /var/lib/mysql/log/mysqld.log: Header page consists of zero bytes in datafile: ./ibdata1
# причина — жёсткое выключение ВМ; данные пересоздаются из dump.sql
systemctl stop mysqld
mv /var/lib/mysql/db /var/lib/mysql/db.broken-$(date +%F)
mkdir /var/lib/mysql/db
chown mysql:mysql /var/lib/mysql/db && chmod 750 /var/lib/mysql/db
systemctl start mysqld
systemctl status mysqld --no-pager | head -3
# затем повторите блок «LAMP и база webdb»"""),
   ]),
 S('m2t8', '8', 'Статическая трансляция портов', 'Задание 8',
   'Таблица nftables из задания 8 Модуля 1 дополняется цепочкой prerouting (DNAT), файл <code>/etc/nftables/nftables.nft</code> перезаписывается целиком. Условие <code>ip daddr</code> вместо <code>iifname</code> позволяет проверять проброс и из своего офиса (с HQ-CLI).',
   [B(['HQ-RTR'], 'DNAT на HQ-SRV', nft('@HQ_WAN_IF@', ['ip daddr @HQ_WAN_IP@ tcp dport @EXT_PORT@ dnat to @HQ_SRV_IP@:@WEB_PORT@', 'ip daddr @HQ_WAN_IP@ tcp dport @SSH_PORT@ dnat to @HQ_SRV_IP@:@SSH_PORT@'])),
    B(['BR-RTR'], 'DNAT на BR-SRV', nft('@BR_WAN_IF@', ['ip daddr @BR_WAN_IP@ tcp dport @EXT_PORT@ dnat to @BR_SRV_IP@:@APP_PORT@', 'ip daddr @BR_WAN_IP@ tcp dport @SSH_PORT@ dnat to @BR_SRV_IP@:@SSH_PORT@'])),
    B(['ISP'], 'Проверка извне', "curl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_WAN_IP@:@EXT_PORT@\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_WAN_IP@:@EXT_PORT@\nssh -p @SSH_PORT@ sshuser@@HQ_WAN_IP@ hostname\nssh -p @SSH_PORT@ sshuser@@BR_WAN_IP@ hostname", check=True,
      expect="200, 200, @H_HQSRV@, @H_BRSRV@"),
    B(['HQ-CLI'], 'Проверка из офиса HQ', "curl -s -o /dev/null -w '%{http_code}\\n' http://@HQ_WAN_IP@:@EXT_PORT@\ncurl -s -o /dev/null -w '%{http_code}\\n' http://@BR_WAN_IP@:@EXT_PORT@", check=True,
      expect="200, 200 (при iifname первая проверка не проходила бы)"),
   ]),
 S('m2t9', '9', 'Яндекс Браузер на HQ-CLI', 'Задание 9', 'Пакет есть в репозитории ALT; другой вариант — «Центр приложений». Для отчёта нужен скриншот запущенного окна.',
   [B(['HQ-CLI'], 'Установка', 'apt-get update && apt-get install -y yandex-browser-stable\nyandex-browser-stable --version', expect="Yandex Browser 25.x")]),
]

CERTS = '/home/sshuser/certs'
def revproxy(tls):
    """Конфигурация nginx на ISP: web — через HQ-RTR (DNAT на HQ-SRV), docker — через BR-RTR (DNAT на BR-SRV)."""
    hdr = "        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
    auth = "    auth_basic \"Authorized access only\";\n    auth_basic_user_file /etc/nginx/.htpasswd;\n"
    def srv(name, up, a, cert):
        s = "server {\n"
        s += ("    listen 443 ssl;\n    server_name %s.@DOMAIN@;\n    ssl_certificate     /etc/nginx/ssl/%s.crt;\n    ssl_certificate_key /etc/nginx/ssl/%s.key;\n" % (name, cert, cert)) if tls else ("    listen 80;\n    server_name %s.@DOMAIN@;\n" % name)
        s += (auth if a else '') + "    location / {\n        proxy_pass http://%s:@EXT_PORT@;\n%s    }\n}\n" % (up, hdr)
        return s
    head = "server {\n    listen 80;\n    server_name web.@DOMAIN@ docker.@DOMAIN@;\n    return 301 https://$host$request_uri;\n}\n" if tls else ''
    return ("cat > /etc/nginx/sites-available.d/revproxy.conf << 'EOF'\n" + head + srv('web', '@HQ_WAN_IP@', tls or AUTH_STEP, 'web') + srv('docker', '@BR_WAN_IP@', False, 'docker') +
            "EOF\nln -sf /etc/nginx/sites-available.d/revproxy.conf /etc/nginx/sites-enabled.d/revproxy.conf\nrm -f /etc/nginx/sites-enabled.d/default.conf\nnginx -t && systemctl restart nginx")
AUTH_STEP = False
REV_HTTP = revproxy(False)
AUTH_STEP = True
REV_AUTH = revproxy(False)
REV_TLS = revproxy(True)

M3 = [
 S('m3t1', '1', 'Импорт пользователей в домен', 'Задание 1',
   'Скрипт <code>import.sh</code> и <code>users.csv</code> лежат на Additional.iso. Файлы сохранены с переводами строк Windows (CRLF): без исправления bash падает с ошибкой «синтаксическая ошибка рядом с неожиданным маркером <code>done</code>». Образ смонтирован только для чтения, поэтому файлы копируются в <code>/root/import</code>.',
   [B(['BR-SRV'], 'Импорт из users.csv', ISO + """mkdir -p /root/import
cp @ISO_DIR@/import.sh @ISO_DIR@/users.csv /root/import/
cd /root/import
# CRLF → LF, иначе «неожиданный маркер done»
sed -i 's/\\r$//' import.sh users.csv
chmod +x import.sh
bash import.sh users.csv"""),
    B(['BR-SRV'], 'Проверка', "samba-tool user list | wc -l\nsamba-tool ou list\nsamba-tool user list | sort | head", check=True,
      expect='сотни пользователей (на стенде — 305 вместе со служебными и hquser), OU CloudStorage, IT, Manager, Overal, Supporter'),
   ]),
 S('m3t2', '2', 'Обратный прокси-сервер на ISP', 'Задание 2',
   'Nginx на ISP принимает запросы к <code>web.@DOMAIN@</code> и <code>docker.@DOMAIN@</code> (обе записи в DNS HQ-SRV указывают на ISP). ISP не знает внутренних сетей офисов, поэтому запросы уходят на внешние адреса маршрутизаторов и дальше по DNAT из задания 8 Модуля 2. В ALT конфигурации лежат в <code>sites-available.d</code> / <code>sites-enabled.d</code>.',
   [B(['ISP'], 'Nginx как reverse proxy', "apt-get update && apt-get install -y nginx\nsystemctl enable --now nginx\n\n" + REV_HTTP),
    B(['ISP'], 'Проверка', "curl -s -H 'Host: web.@DOMAIN@' http://127.0.0.1/ | grep -i '<title>'\ncurl -s -H 'Host: docker.@DOMAIN@' http://127.0.0.1/ | grep -i '<title>'", check=True,
      expect='<title> сайта Apache с HQ-SRV и <title> testapp с BR-SRV («Все студенты»)'),
   ]),
 S('m3t3', '3', 'Web-аутентификация на ISP', 'Задание 3',
   'Basic Auth в nginx только для <code>web.@DOMAIN@</code>: пользователь <code>@WEB_USER@</code>, пароль <code>@PW@</code>. Утилита <code>htpasswd</code> в ALT — пакет <code>apache2-htpasswd</code>. Файл пересобирается целиком, поэтому блок можно выполнять повторно.',
   [B(['ISP'], 'Файл паролей и auth_basic', "apt-get install -y apache2-htpasswd\n# -b — пароль в команде; без -b htpasswd спросит его дважды\nhtpasswd -cb /etc/nginx/.htpasswd @WEB_USER@ '@PW@'\n\n" + REV_AUTH),
    B(['ISP'], 'Проверка', "curl -s -o /dev/null -w '%{http_code}\\n' -H 'Host: web.@DOMAIN@' http://127.0.0.1/\ncurl -s -o /dev/null -w '%{http_code}\\n' -u '@WEB_USER@:@PW@' -H 'Host: web.@DOMAIN@' http://127.0.0.1/", check=True,
      expect='401 без пароля, 200 с паролем'),
   ]),
 S('m3t4', '4', 'Центр сертификации и HTTPS', 'Задание 4',
   'ЦС на HQ-SRV (OpenSSL, RSA; на ДЭ с КриптоПро — ГОСТ). Сертификаты <code>web</code> и <code>docker</code> на @CA_DAYS@ дней с SAN, ключи и сертификаты забираются на ISP через проброс SSH HQ-RTR (задание 8 Модуля 2), корневой сертификат — в доверенные на HQ-CLI. В ALT доверие добавляется через <code>/etc/pki/ca-trust/source/anchors</code> и <code>update-ca-trust</code> (не <code>update-ca-certificates</code>).',
   [B(['HQ-SRV'], 'Корневой ЦС и сертификаты web, docker', """mkdir -p /etc/ssl/ca && cd /etc/ssl/ca
[ -f ca.key ] || openssl genrsa -out ca.key 4096
chmod 600 ca.key
openssl req -x509 -new -key ca.key -sha256 -days @CA_DAYS@ -out ca.crt \\
  -subj "/CN=@WG@ CA" \\
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
for n in web docker; do
  openssl genrsa -out $n.key 2048
  openssl req -new -key $n.key -out $n.csr -subj "/CN=$n.@DOMAIN@"
  printf 'subjectAltName=DNS:%s.@DOMAIN@\\nextendedKeyUsage=serverAuth\\n' $n > $n.ext
  openssl x509 -req -in $n.csr -CA ca.crt -CAkey ca.key -CAcreateserial \\
    -out $n.crt -days @CA_DAYS@ -sha256 -extfile $n.ext
done
openssl x509 -in web.crt -noout -subject -issuer -dates -ext subjectAltName
openssl verify -CAfile ca.crt web.crt docker.crt""",
      expect='web.crt: OK, docker.crt: OK; notAfter — через @CA_DAYS@ дней'),
    B(['HQ-SRV'], 'Выложить файлы для ISP и HQ-CLI', """install -d -o sshuser -g sshuser -m 700 @CERTS@
cp /etc/ssl/ca/{ca.crt,web.crt,web.key,docker.crt,docker.key} @CERTS@/
chown sshuser:sshuser @CERTS@/*
ls -l @CERTS@""".replace('@CERTS@', CERTS)),
    B(['ISP'], 'Сертификаты и HTTPS в nginx', """mkdir -p /etc/nginx/ssl && cd /etc/nginx/ssl
# через DNAT HQ-RTR (@HQ_WAN_IP@:@SSH_PORT@ → HQ-SRV)
scp -P @SSH_PORT@ -o StrictHostKeyChecking=accept-new 'sshuser@@HQ_WAN_IP@:certs/*' .
chown root:root /etc/nginx/ssl/*
chmod 600 /etc/nginx/ssl/*.key

""" + REV_TLS),
    B(['HQ-CLI'], 'Доверие к ЦС', """scp -P @SSH_PORT@ sshuser@@HQ_SRV_IP@:certs/ca.crt /tmp/ca.crt
cp /tmp/ca.crt /etc/pki/ca-trust/source/anchors/au-team-ca.crt
update-ca-trust
trust list | grep -B3 -A2 '@WG@ CA'""", expect='label: @WG@ CA, trust: anchor, category: authority'),
    B(['HQ-CLI'], 'Если браузер не доверяет ЦС (база NSS пользователя)', """# выполнять от имени пользователя, который открывает браузер (не root)
sudo apt-get install -y nss-utils
mkdir -p ~/.pki/nssdb
[ -f ~/.pki/nssdb/cert9.db ] || certutil -d sql:$HOME/.pki/nssdb -N --empty-password
certutil -d sql:$HOME/.pki/nssdb -A -t 'C,,' -n '@WG@ CA' -i /tmp/ca.crt
certutil -d sql:$HOME/.pki/nssdb -L"""),
    B(['HQ-SRV'], 'Убрать закрытые ключи из каталога обмена', "rm -f %s/*.key\nls -l %s" % (CERTS, CERTS)),
    B(['HQ-CLI'], 'Проверка', """curl -sI http://web.@DOMAIN@ | head -1
curl -s -o /dev/null -w '%{http_code}\\n' https://web.@DOMAIN@
curl -s -o /dev/null -w '%{http_code}\\n' -u '@WEB_USER@:@PW@' https://web.@DOMAIN@
curl -s -o /dev/null -w '%{http_code}\\n' https://docker.@DOMAIN@
echo | openssl s_client -connect web.@DOMAIN@:443 -servername web.@DOMAIN@ 2>/dev/null | openssl x509 -noout -issuer -dates""", check=True,
      expect='301 (редирект на HTTPS); 401; 200; 200 — без ошибок сертификата; issuer=CN=@WG@ CA, срок @CA_DAYS@ дней'),
   ]),
 S('m3t5', '5', 'Мониторинг atop', 'Задание 5',
   'Интервал записи — 7 минут (@ATOP_INT@ с). В ALT файл <code>/etc/default/atop</code> изначально пуст, а параметр называется <code>LOGINTERVAL</code>: <code>sed</code> по <code>INTERVAL=</code> ничего не меняет, строку нужно дописать. Значение должно быть в файле, а не только в консоли, — иначе после перезагрузки оно сбросится.',
   [B(['HQ-SRV'], 'Установка и интервал', """apt-get install -y atop
touch /etc/default/atop
if grep -qE '^(LOG)?INTERVAL=' /etc/default/atop; then
  sed -i -E 's/^(LOG)?INTERVAL=.*/LOGINTERVAL=@ATOP_INT@/' /etc/default/atop
else
  echo 'LOGINTERVAL=@ATOP_INT@' >> /etc/default/atop
fi
cat /etc/default/atop
systemctl enable --now atop
systemctl restart atop"""),
    B(['HQ-SRV'], 'Проверка (и после перезагрузки)', "systemctl is-enabled atop\nps -o args= -C atop", check=True,
      expect='enabled; /usr/bin/atop -w /var/log/atop/atop_ГГГГММДД @ATOP_INT@'),
   ]),
 S('m3t6', '6', 'Принт-сервер CUPS', 'Задание 6',
   'Виртуальный PDF-принтер на HQ-SRV (пакет <code>cups-pdf</code>), общий доступ из сети; на HQ-CLI принтер подключается по IPP и назначается принтером по умолчанию. Готовые файлы — в <code>/var/spool/cups-pdf/</code> на HQ-SRV.',
   [B(['HQ-SRV'], 'CUPS и принтер PDF', """apt-get install -y cups cups-pdf
systemctl enable --now cups
lpinfo -v | grep cups-pdf
# доступ из сети и общий доступ к принтерам
cupsctl --share-printers --remote-any
sed -i 's/^Listen localhost:631/Port 631/' /etc/cups/cupsd.conf
systemctl restart cups
lpstat -p PDF >/dev/null 2>&1 || lpadmin -p PDF -E -v cups-pdf:/ -m CUPS-PDF.ppd -o printer-is-shared=true
lpadmin -d PDF
lpstat -t""", expect='предупреждение «Printer drivers are deprecated» не мешает; принтер PDF принимает запросы'),
    B(['HQ-CLI'], 'Подключение и принтер по умолчанию', """lpstat -p PDF-Printer >/dev/null 2>&1 || lpadmin -p PDF-Printer -E -v ipp://@H_HQSRV@:631/printers/PDF -m everywhere
lpadmin -d PDF-Printer
lpoptions -d PDF-Printer >/dev/null
lpstat -d -p""", expect='назначение системы по умолчанию: PDF-Printer'),
    B(['HQ-CLI'], 'Проверка: печать в PDF', "echo 'test print' | lp\nlpstat -W completed | tail -2\n# на HQ-SRV: ls -lR /var/spool/cups-pdf/", check=True,
      expect='задание PDF-Printer-N выполнено, на HQ-SRV появился .pdf'),
   ]),
 S('m3t7', '7', 'Инвентаризация через Ansible', 'Задание 7',
   'Плейбук на BR-SRV собирает имя и IP HQ-SRV и HQ-CLI и сохраняет их <b>на BR-SRV</b> в <code>/etc/ansible/PC-INFO/&lt;хост&gt;.yml</code> — для этого задача делегируется на <code>localhost</code>. Использует инвентарь из задания 5 Модуля 2.',
   [B(['BR-SRV'], 'Плейбук inventory.yml', """mkdir -p /etc/ansible/PC-INFO /etc/ansible/playbook
cat > /etc/ansible/playbook/inventory.yml << 'EOF'
- name: Инвентаризация HQ-SRV и HQ-CLI
  hosts: hq-srv,hq-cli
  gather_facts: yes
  tasks:
    - name: Сохранение имени и IP на BR-SRV
      copy:
        content: |
          hostname: {{ ansible_fqdn }}
          ip_address: {{ ansible_default_ipv4.address }}
        dest: "/etc/ansible/PC-INFO/{{ inventory_hostname }}.yml"
      delegate_to: localhost
EOF
ansible-playbook /etc/ansible/playbook/inventory.yml"""),
    B(['BR-SRV'], 'Проверка', "ls -l /etc/ansible/PC-INFO/\ncat /etc/ansible/PC-INFO/*.yml", check=True,
      expect='hq-cli.yml, hq-srv.yml; hostname: @H_HQCLI@, ip_address: @HQ_CLI_IP@; hostname: @H_HQSRV@, ip_address: @HQ_SRV_IP@'),
   ]),
 S('m3t8', '8', 'Защита SSH: fail2ban', 'Задание 8',
   'Jail <code>sshd</code> на порту @SSH_PORT@ (не 22!), @F2B_RETRY@ попытки, блокировка @F2B_BAN@ с (в новых версиях bantime — в секундах). В ALT журнал sshd читается через systemd (<code>backend = systemd</code>, нужен <code>python3-module-systemd</code>), блокировка — через nftables.',
   [B(['HQ-SRV'], 'Установка и jail.local', """apt-get install -y fail2ban python3-module-systemd nftables
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
backend   = systemd
banaction = nftables-multiport
ignoreip  = 127.0.0.1/8

[sshd]
enabled  = true
port     = @SSH_PORT@
filter   = sshd
maxretry = @F2B_RETRY@
findtime = 600
bantime  = @F2B_BAN@
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban
fail2ban-client status sshd"""),
    B(['HQ-CLI'], 'Проверка: несколько неверных паролей', "# введите неверный пароль, пока соединение не перестанет устанавливаться\nssh -p @SSH_PORT@ sshuser@@HQ_SRV_IP@\nssh -p @SSH_PORT@ sshuser@@HQ_SRV_IP@", check=True,
      expect='после @F2B_RETRY@ неудач — Connection refused/timeout на @F2B_BAN@ с'),
    B(['HQ-SRV'], 'Проверка: адрес заблокирован', "fail2ban-client status sshd\nnft list ruleset | grep -A3 f2b\n# снять блокировку досрочно:\n# fail2ban-client set sshd unbanip @HQ_CLI_IP@", check=True,
      expect='Currently banned: 1, Banned IP list: @HQ_CLI_IP@'),
   ]),
 S('m3t9', '9', 'Резервное копирование BorgBackup', 'Задание 9',
   'Аналог «Кибер Бэкап» с защитой от шифровальщиков: HQ-SRV отправляет <code>/etc</code> в репозиторий на HQ-CLI. Ключ HQ-SRV на HQ-CLI ограничен командой <code>borg serve --append-only --restrict-to-path /backup</code>: заражённый HQ-SRV может добавлять архивы, но не удалять и не перезаписывать старые. Репозиторий зашифрован (<code>repokey</code>), копия — ежедневно по таймеру systemd.',
   [B(['HQ-SRV', 'HQ-CLI'], 'Пакет borg', 'apt-get install -y borg\nborg --version'),
    B(['HQ-CLI'], 'Пользователь borguser и каталог /backup', """id borguser >/dev/null 2>&1 || useradd -m -s /bin/bash borguser
mkdir -p /backup && chown borguser:borguser /backup && chmod 700 /backup
# если в sshd задан AllowUsers — добавить borguser
if grep -q '^AllowUsers' /etc/openssh/sshd_config && ! grep -q '^AllowUsers.*borguser' /etc/openssh/sshd_config; then
  sed -i '/^AllowUsers/ s/$/ borguser/' /etc/openssh/sshd_config
  sshd -t && systemctl restart sshd
fi"""),
    B(['HQ-SRV'], 'Ключ SSH и пароль репозитория', """[ -f /root/.ssh/borg_key ] || ssh-keygen -t ed25519 -N '' -f /root/.ssh/borg_key
echo '@PW@' > /root/.borg-pass && chmod 600 /root/.borg-pass
scp -P @ANS_PORT@ /root/.ssh/borg_key.pub sshuser@@HQ_CLI_IP@:/tmp/"""),
    B(['HQ-CLI'], 'Ключ только для borg serve --append-only, репозиторий', """mkdir -p /home/borguser/.ssh
grep -qF "$(cut -d' ' -f2 /tmp/borg_key.pub)" /home/borguser/.ssh/authorized_keys 2>/dev/null || \\
  echo "command=\\"borg serve --append-only --restrict-to-path /backup\\",restrict $(cat /tmp/borg_key.pub)" >> /home/borguser/.ssh/authorized_keys
chown -R borguser:borguser /home/borguser/.ssh
chmod 700 /home/borguser/.ssh && chmod 600 /home/borguser/.ssh/authorized_keys
[ -d /backup/hq-srv ] || sudo -u borguser BORG_PASSPHRASE='@PW@' borg init --encryption=repokey /backup/hq-srv"""),
    B(['HQ-SRV'], 'Скрипт и ежедневный таймер', """cat > /usr/local/bin/backup-etc.sh << 'EOF'
#!/bin/bash
export BORG_RSH='ssh -i /root/.ssh/borg_key -p @ANS_PORT@ -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes'
export BORG_PASSCOMMAND='cat /root/.borg-pass'
REPO='ssh://borguser@@HQ_CLI_IP@:@ANS_PORT@/backup/hq-srv'
borg create --stats --compression lz4 "$REPO::etc-{now:%Y-%m-%d_%H%M}" /etc
EOF
chmod 700 /usr/local/bin/backup-etc.sh
cat > /etc/systemd/system/backup-etc.service << 'EOF'
[Unit]
Description=Backup /etc to HQ-CLI (borg)
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup-etc.sh
EOF
cat > /etc/systemd/system/backup-etc.timer << 'EOF'
[Unit]
Description=Daily backup /etc
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload && systemctl enable --now backup-etc.timer
/usr/local/bin/backup-etc.sh
systemctl list-timers backup-etc.timer"""),
    B(['HQ-SRV'], 'Проверка: список архивов и восстановление', """export BORG_RSH='ssh -i /root/.ssh/borg_key -p @ANS_PORT@ -o IdentitiesOnly=yes'
export BORG_PASSCOMMAND='cat /root/.borg-pass'
R='ssh://borguser@@HQ_CLI_IP@:@ANS_PORT@/backup/hq-srv'
borg list "$R"
mkdir -p /tmp/restore && cd /tmp/restore
borg extract "$R::$(borg list --short "$R" | tail -1)" etc/hostname
cat /tmp/restore/etc/hostname""", check=True,
      expect='архив etc-ГГГГ-ММ-ДД_ЧЧММ; восстановленный etc/hostname содержит @H_HQSRV@'),
    B(['HQ-CLI'], 'Проверка: ключ HQ-SRV ограничен append-only', "grep -o 'command=\"[^\"]*\"' /home/borguser/.ssh/authorized_keys\nls -ld /backup /backup/hq-srv", check=True,
      expect='command="borg serve --append-only --restrict-to-path /backup"; владелец borguser, права 700 — с HQ-SRV удалить старые архивы нельзя'),
   ]),
]

DEV = {'ISP': 'isp', 'HQ-RTR': 'hq', 'HQ-SRV': 'hq', 'HQ-CLI': 'hq', 'BR-RTR': 'br', 'BR-SRV': 'br', 'Все ВМ': 'all'}
DEVS = ['ISP', 'HQ-RTR', 'HQ-SRV', 'HQ-CLI', 'BR-RTR', 'BR-SRV']

def render_steps(steps):
    toc, body = [], []
    for s in steps:
        toc.append('<li><a href="#%s" data-step="%s"><span class="n">%s</span><span class="tt">%s</span><span class="cnt" data-cnt="%s"></span></a></li>' % (s['id'], s['id'], s['num'], T(s['title']), s['id']))
        bl = []
        for i, b in enumerate(s['blocks']):
            bid = '%s-%d' % (s['id'], i + 1)
            badges = ''.join('<span class="dev d-%s">%s</span>' % (DEV[d], E(d)) for d in b['devs'])
            kind = ' chk' if b['check'] else ''
            exp = '<div class="exp"><span class="expl">Ожидается</span><div class="expt">%s</div></div>' % T(b['expect']) if b['expect'] else ''
            bl.append('''<div class="block%s" id="%s" data-dev="%s" data-kind="%s">
<div class="bh"><label class="done" title="Отметить как выполненное"><input type="checkbox" aria-label="Готово: %s"><span class="box" aria-hidden="true"></span></label><div class="bt">%s<span class="btitle">%s</span></div><button class="copy" type="button">Копировать</button></div>
<pre><code>%s</code></pre>%s</div>''' % (kind, bid, E('|'.join(b['devs'])), 'check' if b['check'] else 'cmd', E(plain(b['title'])), badges, T(b['title']), hl(b['code']), exp))
        body.append('''<section class="step" id="%s" data-num="%s" data-title="%s">
<div class="sh"><span class="snum">%s</span><div><div class="exam">%s</div><h3>%s</h3></div></div>
<p class="sd">%s</p>
%s
</section>''' % (s['id'], E(s['num']), E(plain(s['title'])), s['num'], E(s['exam']), T(s['title']), tok(s['desc']), ''.join(bl)))
    return '\n'.join(toc), '\n'.join(body)

def render_docs(path):
    s = open(path, encoding='utf-8').read()
    parts = re.split(r'(<svg.*?</svg>)', s, flags=re.S)
    return ''.join(tok(p, 'tspan') if p.startswith('<svg') else tok(p) for p in parts)

def doc_toc(pairs): return '\n'.join('<li><a href="#%s"><span class="n">·</span><span class="tt">%s</span></a></li>' % p for p in pairs)

VERSION = '1.4'
SHELL = open(SRC + '/shell.html', encoding='utf-8').read()
HOME = open(SRC + '/home.html', encoding='utf-8').read()
PH = re.compile(r'\{\{([A-Z0-9_]+)\}\}')
def fill(tpl, vals):
    # один проход: вставленный текст (например, {{ ansible_fqdn }} в командах) повторно не разбирается
    return PH.sub(lambda m: vals[m.group(1)], tpl)

# ---------- страницы сайта ----------
# Имена файлов: index.html — главная; m<N>-<тема>.html — модуль N. Префикс m<N> совпадает с PAGE_ID
# (ключ отметок «готово» stand.done.v1.m<N>), поэтому при сортировке по имени файлы идут по порядку модулей.
PAGES = [
 dict(pid='m1', file='m1-network.html', num='1', name='Настройка сетевой инфраструктуры', steps=M1, docs='docs_m1.html', lessons='№3–9',
      lead='Документация сети и команды настройки — в порядке пунктов Задания 1 КИМ 09.02.06-1-2027 (профильный уровень).',
      dtoc=[('topology', 'Топология'), ('vms', 'Виртуальные машины'), ('addr', 'IP-адресация'), ('vlan', 'VLAN и подсети'), ('services', 'Службы и учётки'), ('dns', 'DNS-записи')],
      card='Адресация, VLAN, GRE и OSPF, NAT, DHCP, DNS, SSH, часовой пояс.'),
 dict(pid='m2', file='m2-admin.html', num='2', name='Организация сетевого администрирования', steps=M2, docs='docs_m2.html', lessons='№10–12',
      lead='Команды в порядке пунктов Задания 2 КИМ 09.02.06-1-2027: домен, хранилище, NFS, время, Ansible, Docker, веб-приложения, проброс портов.',
      dtoc=[('needs', 'Подготовка'), ('services', 'Службы Модуля 2')],
      card='Samba DC и вход в домен, RAID 0, NFS, chrony, Ansible, Docker, Apache + MariaDB, DNAT, Яндекс Браузер.'),
 dict(pid='m3', file='m3-services.html', num='3', name='Эксплуатация объектов сетевой инфраструктуры', steps=M3, docs='docs_m3.html', lessons='№13–15',
      lead='Команды в порядке пунктов Задания 3 КИМ 09.02.06-1-2027: импорт пользователей, обратный прокси и аутентификация, ЦС и HTTPS, мониторинг, печать, инвентаризация, fail2ban, резервное копирование.',
      dtoc=[('needs', 'Подготовка'), ('services', 'Службы Модуля 3')],
      card='Импорт пользователей, nginx reverse proxy с Basic Auth, свой ЦС и HTTPS, atop, CUPS, инвентаризация Ansible, fail2ban, BorgBackup.'),
]
LEGACY = {'module2.html': 'm2-admin.html'}   # старые имена → новые (страницы-переадресации)
FILE = {pg['pid']: pg['file'] for pg in PAGES}

def mods(cur, base=''):
    out = ['<a href="%sindex.html" class="mhome" title="Главная"%s>Главная</a>' % (base, ' aria-current="page"' if cur == 'home' else '')]
    for pg in PAGES:
        out.append('<a href="%s%s" title="Модуль %s. %s"%s>М%s</a>' % (base, pg['file'], pg['num'], pg['name'], ' aria-current="page"' if cur == pg['pid'] else '', pg['num']))
    return ''.join(out)

def pager(i):
    a = []
    if i > 0: a.append('<a class="prev" href="%s"><span>← Модуль %s</span>%s</a>' % (PAGES[i-1]['file'], PAGES[i-1]['num'], PAGES[i-1]['name']))
    else: a.append('<a class="prev" href="index.html"><span>← Главная</span>Обзор стенда</a>')
    if i < len(PAGES) - 1: a.append('<a class="next" href="%s"><span>Модуль %s →</span>%s</a>' % (PAGES[i+1]['file'], PAGES[i+1]['num'], PAGES[i+1]['name']))
    return ''.join(a)

def block_ids(steps): return ['%s-%d' % (st['id'], j + 1) for st in steps for j in range(len(st['blocks']))]

def page(i):
    pg = PAGES[i]; steps = pg['steps']
    for st in steps:
        m = re.match(r'^Задание (\d+)$', st['exam'])
        if m: st['exam'] = 'Задание %s · пункт %s' % (pg['num'], m.group(1))
    toc, body = render_steps(steps)
    filt = ''.join('<button type="button" data-f="%s" aria-pressed="false">%s</button>' % (d, d) for d in DEVS)
    title = 'Модуль %s. %s · стенд au-team.irpo' % (pg['num'], pg['name'])
    out = fill(SHELL, {'PAGE_ID': pg['pid'], 'TITLE': title, 'DESC': E(pg['lead']), 'H1': '<em>Модуль %s</em> %s' % (pg['num'], pg['name']), 'LEAD': pg['lead'],
                       'DOCS': render_docs(SRC + '/' + pg['docs']), 'DOC_TOC': doc_toc(pg['dtoc']), 'TOC': toc, 'STEPS': body, 'FILTER': filt,
                       'SITE_URL': SITE_URL, 'OG_URL': SITE_URL + pg['file'], 'MODS': mods(pg['pid']), 'PAGER': pager(i)})
    open(os.path.join(OUT, pg['file']), 'w', encoding='utf-8').write(out)
    return len(out)

# ---------- главная ----------
LESSONS = [
 ('3', 'Развёртывание стенда и L2', [('m1', 'prep', 'Подготовка')], 'pre-lab4'),
 ('4', 'Конфигурация узла и ужесточение доступа', [('m1', 't1', 'М1 п.1'), ('m1', 't3', 'п.3'), ('m1', 't5', 'п.5'), ('m1', 't11', 'п.11')], 'pre-lab5'),
 ('5', 'VLAN 802.1Q и меж-VLAN маршрутизация', [('m1', 't4', 'М1 п.4')], 'pre-lab6'),
 ('6', 'Петли, STP и защита L2', [], '—'),
 ('7', 'ISP и доступ в Интернет', [('m1', 't2', 'М1 п.2')], 'pre-lab8'),
 ('8', 'GRE-туннель, OSPF с MD5, NAT', [('m1', 't6', 'М1 п.6'), ('m1', 't7', 'п.7'), ('m1', 't8', 'п.8')], 'pre-lab9'),
 ('9', 'DHCP, DNS и финальная сверка', [('m1', 't9', 'М1 п.9'), ('m1', 't10', 'п.10'), ('m1', 'check', 'проверка')], 'task1-done'),
 ('10', 'Домен, пользователи, политики и время', [('m2', 'm2t1', 'М2 п.1'), ('m2', 'm2t4', 'п.4')], 'dc-ready, pre-lab11'),
 ('11', 'RAID, NFS и Ansible', [('m2', 'm2t2', 'М2 п.2'), ('m2', 'm2t3', 'п.3'), ('m2', 'm2t5', 'п.5')], 'pre-lab12'),
 ('12', 'Docker, веб-приложение, DNAT и браузер', [('m2', 'm2t6', 'М2 п.6'), ('m2', 'm2t7', 'п.7'), ('m2', 'm2t8', 'п.8'), ('m2', 'm2t9', 'п.9')], 'task2-done'),
 ('13', 'Импорт пользователей, reverse proxy, web-аутентификация', [('m3', 'm3t1', 'М3 п.1'), ('m3', 'm3t2', 'п.2'), ('m3', 'm3t3', 'п.3')], 'pre-lab14 *'),
 ('14', 'Центр сертификации, мониторинг и печать', [('m3', 'm3t4', 'М3 п.4'), ('m3', 'm3t5', 'п.5'), ('m3', 'm3t6', 'п.6')], 'pre-lab15 *'),
 ('15', 'Автоматизация, защита SSH и бэкап', [('m3', 'm3t7', 'М3 п.7'), ('m3', 'm3t8', 'п.8'), ('m3', 'm3t9', 'п.9')], 'task3-done *'),
]
CARD = '''<a class="mcard" href="%s" data-mod="%s" data-blocks="%s">
<span class="mk"><span class="mnum">%s</span>Задание %s КИМ · занятия %s</span>
<span class="mt">%s</span><span class="md">%s</span>
<span class="mstat">%d шагов · %d блоков</span>
<span class="mprog" aria-hidden="true"><span data-bar></span></span><span class="mdone" data-done>не начат</span></a>'''

def home():
    cards = []
    for pg in PAGES:
        ids = block_ids(pg['steps'])
        cards.append(CARD % (pg['file'], pg['pid'], ' '.join(ids), pg['num'], pg['num'], pg['lessons'], E(pg['name']), E(pg['card']), len(pg['steps']), len(ids)))
    les = '\n'.join('<tr><td class="m">%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>' % (
        n, E(t), ' · '.join('<a href="%s#%s">%s</a>' % (FILE[m], a, E(l)) for m, a, l in links) or '<span class="hint">вне КИМ, на сайте нет</span>', E(sn))
        for n, t, links, sn in LESSONS)
    les += '\n<tr><td colspan="4" class="hint">* в паспорте имена снапшотов для занятий №13–15 не заданы — предложены по тому же принципу.</td></tr>'
    m1 = PAGES[0]; idmap = {}
    for x in ['docs', 'kimcheck'] + [d for d, _ in m1['dtoc']] + [st['id'] for st in m1['steps']] + block_ids(m1['steps']): idmap[x] = 'm1'
    tpl = tok(HOME)   # @ТОКЕНЫ@ в статичной части главной
    out = fill(tpl, {'TITLE': 'Стенд au-team.irpo · ДЭ 09.02.06 — главная',
                     'DESC': 'Документация сети и команды настройки учебного стенда (ALT Linux) по трём модулям демоэкзамена 09.02.06. Команды пересобираются под ваши параметры сети.',
                     'SITE_URL': SITE_URL, 'OG_URL': SITE_URL, 'MODS': mods('home'), 'CARDS': '\n'.join(cards), 'LESSONS': les,
                     'IDMAP': json.dumps(idmap, separators=(',', ':')), 'FILES': json.dumps(FILE, separators=(',', ':')), 'VERSION': VERSION})
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(out)
    return len(out)

REDIRECT = '''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Страница переехала</title>
<meta name="robots" content="noindex"><link rel="canonical" href="%(url)s">
<meta http-equiv="refresh" content="0; url=%(to)s">
<script>location.replace("%(to)s" + location.hash);</script></head>
<body><p>Страница переехала: <a href="%(to)s">%(to)s</a></p></body></html>
'''
NOTFOUND = '''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Страница не найдена · стенд au-team.irpo</title><meta name="robots" content="noindex">
<link rel="icon" type="image/png" href="%(base)sassets/favicon.png"><link rel="stylesheet" href="%(base)sassets/style.css">
<script>/* module1.html, module3.html и т. п. → m<N>-*.html */
(function(){var f=%(files)s,m=location.pathname.match(/module(\\d)\\.html$/);if(m&&f["m"+m[1]])location.replace(location.pathname.replace(/[^\\/]*$/,"")+f["m"+m[1]]+location.hash);})();</script>
</head><body class="home"><div class="hwrap"><header class="hhero"><div>
<p class="kicker">Ошибка 404</p><h1>Страница не найдена</h1>
<p class="hlead">Адреса страниц изменились в версии 1.4. Выберите раздел:</p>
<nav class="mods hmods" aria-label="Разделы сайта">%(mods)s</nav></div></header></div></body></html>
'''

os.makedirs(OUT + '/assets', exist_ok=True)
for f in ('params.js', 'app.js', 'style.css', 'home.js'): shutil.copy(SRC + '/' + f, OUT + '/assets/' + f)
sizes = [page(i) for i in range(len(PAGES))]
hsize = home()
for old, new in LEGACY.items():
    open(os.path.join(OUT, old), 'w', encoding='utf-8').write(REDIRECT % {'to': new, 'url': SITE_URL + new})
# 404 открывается GitHub Pages по любому пути, поэтому ссылки в нём абсолютные (если задан SITE_URL)
base = '' if 'USERNAME' in SITE_URL else SITE_URL
open(os.path.join(OUT, '404.html'), 'w', encoding='utf-8').write(NOTFOUND % {'base': base, 'files': json.dumps(FILE), 'mods': mods('', base)})
print('ok home %d %s blocks %s' % (hsize, ' '.join('%s %d' % (pg['file'], n) for pg, n in zip(PAGES, sizes)), '/'.join(str(len(block_ids(pg['steps']))) for pg in PAGES)))
