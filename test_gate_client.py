import unittest

from gate_client import check_plate, should_open_gate


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(self.payload)


class GateClientTest(unittest.TestCase):
    def test_gate_open_is_the_final_open_decision(self):
        self.assertFalse(should_open_gate({
            "is_resident": True,
            "is_registered": True,
            "gate_open": False,
        }))
        self.assertTrue(should_open_gate({
            "is_resident": False,
            "is_registered": True,
            "gate_open": True,
        }))

    def test_check_plate_sends_apartment_no_to_fastapi(self):
        session = FakeSession({
            "plate": "12가1234",
            "is_registered": True,
            "gate_open": True,
            "reason": "등록 차량입니다.",
        })

        result = check_plate(
            "12가1234",
            session=session,
            base_url="http://127.0.0.1:8000",
            apartment_no=1,
        )

        self.assertTrue(result["gate_open"])
        self.assertTrue(result["is_registered"])
        self.assertEqual(session.calls[0]["url"], "http://127.0.0.1:8000/api/check-plate")
        self.assertEqual(session.calls[0]["json"], {
            "plate": "12가1234",
            "apartment_no": 1,
        })


if __name__ == "__main__":
    unittest.main()
