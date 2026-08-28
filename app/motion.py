"""Hareket motoru: tek saat, yaylar, geçişler, efektler.

Uygulamada dört ayrı `QTimer` vardı ve her biri hareketi **kare başına**
sabit bir adımla yürütüyordu:

    x += (hedef - x) * 0.18

Bu satır yanlış. Kare düşerse animasyon yavaşlıyor, hızlı bir makinede
hızlanıyor; süresi donanıma bağlı oluyor. Buradaki her şey **geçen
zamana** göre ilerliyor: 30 fps'te de 120 fps'te de aynı sürede varıyor.
Ölçüldü, testi var.

Tek bir saat var ve abonesi kalmayınca duruyor. Dört zamanlayıcı boşta
dönmüyor artık.

Parçalar:

- `Spring` — hedefe koşan sönümlü yay. Süre vermiyorsun, sertlik
  veriyorsun; yolun ortasında hedef değişirse hız korunuyor. Süreli bir
  geçiş orada sıfırlanıp zıplardı.
- `Tween` — belli süreli geçiş, yumuşatma eğrisiyle. Girişi biten,
  kesilmeyecek hareketler için.
- `Shake` — sönümlü titreme. Hata için.
- `Ripple` — merkezden yayılıp sönen halka. Tek atımlık, tıklama gibi
  anlık olaylar için.
"""

from __future__ import annotations

import math
import time
import weakref
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

#: Hedef kare aralığı, milisaniye. 60 fps.
TICK_MS = 16

#: Bir karede hesaplanacak en uzun süre. Uygulama duraksadıktan sonra
#: (pencere sürüklerken, ağır bir araç çalışırken) `dt` yarım saniye
#: gelebiliyor. Sınır, o sıçramayı yutuyor.
MAX_DT = 0.05

#: Yayın tek seferde ilerleyeceği en uzun süre.
#:
#: Yalnızca `MAX_DT` ile denedim ve yetmedi: `stiffness=400`,
#: `damping=40` ve `dt=0.05`'te sönüm terimi `1 - damping*dt = -1`
#: oluyor, yani hız her adımda işaret değiştirip büyüyor. Otuz adımda
#: değer -514228'e uçtu. Yarı örtük Euler'in kararlılık koşulu
#: `dt < 2/damping`; alt adım bunu garanti ediyor ve sonucu kare
#: süresinden bağımsız kılıyor.
SUBSTEP = 1.0 / 240.0


# --- yumuşatma eğrileri ----------------------------------------------------

def ease_out_expo(t: float) -> float:
    """Hızlı çıkıp yumuşak duran eğri. Emin varışlar için."""
    return 1.0 if t >= 1.0 else 1.0 - pow(2, -10 * t)


def ease_out_back(t: float) -> float:
    """Hedefi azıcık aşıp geri gelen eğri. Bir şeyin yerine oturduğunu
    anlatıyor — her yerde kullanılırsa yaylanan bir arayüz olur."""
    c = 1.70158
    u = t - 1.0
    return 1.0 + (c + 1.0) * u * u * u + c * u * u


def ease_in_out(t: float) -> float:
    return 3 * t * t - 2 * t * t * t


def ease_out_cubic(t: float) -> float:
    return 1.0 - pow(1.0 - t, 3)


# --- saat ------------------------------------------------------------------

def _canli(geri: Callable[[float], None]) -> bool:
    """Geri çağrının sahibi hâlâ yaşıyor mu.

    Zayıf başvuru yetmiyor: Qt bir widget'ın **C++ tarafını** silip
    Python sarmalayıcıyı ayakta bırakabiliyor. O durumda `WeakMethod`
    canlı görünüyor, çağrı yapılıyor ve ölü nesneye dokunulduğu anda
    süreç segfault ile düşüyor. Ölçtüm: `del` ve `gc.collect()` sonrası
    abone sayısı hâlâ birdi ve bir sonraki tick onu boyamaya çalıştı.

    Bu kontrol saatte, tek tek widget'larda değil. Her animasyonlu
    widget'a aynı korumayı elle eklemek, birini unutmanın kesin yoluydu.
    """
    sahip = getattr(geri, "__self__", None)
    if sahip is None:
        return True
    try:
        from shiboken6 import isValid
    except ImportError:  # Qt yok — saf mantık testleri
        return True
    try:
        return bool(isValid(sahip))
    except (TypeError, RuntimeError):
        # Qt nesnesi değil: silinmiş olamaz.
        return True


class Clock(QObject):
    """Bütün hareketi süren tek zamanlayıcı.

    Abonesi kalmayınca duruyor: boşta dönen bir zamanlayıcı, hiçbir şey
    olmazken işlemci yakar ve dizüstünde pil yer.
    """

    def __init__(self) -> None:
        super().__init__()
        # Zayıf referans. Güçlü tutmak iki şeyi bozuyordu: widget'lar
        # kapandıktan sonra da yaşıyordu, ve Qt nesnesi C++ tarafında
        # silinince geriye sarkan çağrı kalıp süreci çökertiyordu —
        # ölçtüm, segfault. Zayıf referans ölen aboneyi kendiliğinden
        # düşürüyor.
        self._aboneler: list[weakref.ref] = []
        self._son = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _ref(self, geri: Callable[[float], None]) -> weakref.ref:
        if hasattr(geri, "__self__"):
            return weakref.WeakMethod(geri)
        return weakref.ref(geri)

    def subscribe(self, geri: Callable[[float], None]) -> None:
        if any(r() == geri for r in self._aboneler):
            return
        self._aboneler.append(self._ref(geri))
        if not self._timer.isActive():
            self._son = time.perf_counter()
            self._timer.start(TICK_MS)

    def unsubscribe(self, geri: Callable[[float], None]) -> None:
        self._aboneler = [r for r in self._aboneler
                          if r() is not None and r() != geri]
        if not self._aboneler:
            self._timer.stop()

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        simdi = time.perf_counter()
        dt = min(simdi - self._son, MAX_DT)
        self._son = simdi
        olu = False
        for ref in list(self._aboneler):
            geri = ref()
            if geri is None or not _canli(geri):
                olu = True
                continue
            geri(dt)
        if olu:
            self._aboneler = [r for r in self._aboneler if r() is not None]
            if not self._aboneler:
                self._timer.stop()


_saat: Clock | None = None


def clock() -> Clock:
    """Uygulamanın tek saati."""
    global _saat
    if _saat is None:
        _saat = Clock()
    return _saat


# --- yay -------------------------------------------------------------------

class Spring:
    """Hedefe koşan sönümlü yay.

    `stiffness` ne kadar sert çektiği, `damping` ne kadar çabuk
    durduğudur. `damping = 2*sqrt(stiffness)` kritik sönüm: aşmadan
    varıyor. Altında yaylanıyor, üstünde ağırlaşıyor.

    Yarı örtük Euler kullanılıyor — hızı önce güncelleyip konumu yeni
    hızla taşımak, açık Euler'in yüksek sertlikte patlamasını önlüyor.
    """

    def __init__(self, value: float = 0.0, stiffness: float = 180.0,
                 damping: float | None = None) -> None:
        self.value = value
        self.target = value
        self.velocity = 0.0
        self.stiffness = stiffness
        self.damping = damping if damping is not None else 2 * math.sqrt(stiffness)

    def to(self, target: float) -> None:
        self.target = target

    def jump(self, value: float) -> None:
        """Anında oraya. Yeni bir tur başlarken eskisinin hızını taşımamak
        için."""
        self.value = self.target = value
        self.velocity = 0.0

    def kick(self, hiz: float) -> None:
        """Yaya hız veriyor. Bir şeyin geldiğini anlatmanın en ucuz yolu:
        konum değişmiyor, tepki veriyor."""
        self.velocity += hiz

    def step(self, dt: float) -> float:
        kalan = min(dt, MAX_DT)
        while kalan > 0.0:
            h = SUBSTEP if kalan > SUBSTEP else kalan
            ivme = ((self.target - self.value) * self.stiffness
                    - self.velocity * self.damping)
            self.velocity += ivme * h
            self.value += self.velocity * h
            kalan -= h
        return self.value

    @property
    def resting(self) -> bool:
        return (abs(self.target - self.value) < 0.001
                and abs(self.velocity) < 0.001)


# --- süreli geçiş ----------------------------------------------------------

class Tween:
    """Belli süreli geçiş. Bitince `done` doğru oluyor."""

    def __init__(self, duration: float, ease: Callable[[float], float] = ease_out_expo,
                 delay: float = 0.0) -> None:
        self.duration = max(duration, 0.0001)
        self.ease = ease
        self.delay = delay
        self.elapsed = 0.0

    def step(self, dt: float) -> float:
        self.elapsed += dt
        t = (self.elapsed - self.delay) / self.duration
        return self.ease(max(0.0, min(1.0, t)))

    @property
    def value(self) -> float:
        t = (self.elapsed - self.delay) / self.duration
        return self.ease(max(0.0, min(1.0, t)))

    @property
    def done(self) -> bool:
        return self.elapsed >= self.delay + self.duration


# --- efektler --------------------------------------------------------------

class Shake:
    """Sönümlü titreme. Hata için: kırmızı bir yazı okunmayı bekler,
    titreyen bir şey gözü kendine çeker."""

    def __init__(self, freq: float = 34.0, decay: float = 7.0) -> None:
        self.freq = freq
        self.decay = decay
        self.amount = 0.0
        self.phase = 0.0

    def hit(self, amount: float = 1.0) -> None:
        self.amount = amount
        self.phase = 0.0

    def step(self, dt: float) -> float:
        if self.amount <= 0.0005:
            self.amount = 0.0
            return 0.0
        self.phase += dt
        self.amount *= math.exp(-self.decay * dt)
        return math.sin(self.phase * self.freq) * self.amount

    @property
    def resting(self) -> bool:
        return self.amount <= 0.0005


class Ripple:
    """Merkezden yayılıp sönen tek atım. 0'dan 1'e gidiyor ve bitiyor."""

    def __init__(self, duration: float = 0.55) -> None:
        self.duration = duration
        self.t = 1.0

    def hit(self) -> None:
        self.t = 0.0

    def step(self, dt: float) -> None:
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt / self.duration)

    @property
    def alive(self) -> bool:
        return self.t < 1.0

    @property
    def radius(self) -> float:
        """0 -> 1, yumuşayarak."""
        return ease_out_cubic(self.t)

    @property
    def alpha(self) -> float:
        """1 -> 0, sona doğru hızlanarak."""
        return max(0.0, 1.0 - self.t * self.t)
