try:
    import asyncio
    from datetime import datetime, timedelta
    from typing import Any, ClassVar, Final, Mapping, Optional, Sequence
    from io import BytesIO
    from dotenv import load_dotenv
    import os

    from typing_extensions import Self
    from viam.components.sensor import *
    from viam.module.module import Module
    from viam.proto.app.robot import ComponentConfig
    from viam.proto.common import ResourceName
    from viam.resource.base import ResourceBase
    from viam.resource.easy_resource import EasyResource
    from viam.resource.types import Model, ModelFamily
    from viam.utils import SensorReading
    from viam.robot.client import RobotClient
    from viam.components.camera import Camera
    from viam.components.board import Board
    from viam.rpc.dial import DialOptions, Credentials
    from viam.app.viam_client import ViamClient
    from viam.media.utils.pil import viam_to_pil_image
except ImportError as e:
    raise Exception(f"Error importing modules: {e}")

try:
    load_dotenv()
except Exception as e:
    raise Exception(f"Error loading .env file: {e}")

class Test(Sensor, EasyResource):
    MODEL: ClassVar[Model] = Model(ModelFamily("brad-grigsby", "test-sensor"), "test")

    def __init__(self, name, *, logger = None):
        super().__init__(name, logger=logger)
        self.machine = None
        self.viam_client = None

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        """This method creates a new instance of this Sensor component.
        The default implementation sets the name from the `config` parameter and then calls `reconfigure`.

        Args:
            config (ComponentConfig): The configuration for this resource
            dependencies (Mapping[ResourceName, ResourceBase]): The dependencies (both implicit and explicit)

        Returns:
            Self: The resource
        """
        return super().new(config, dependencies)

    @classmethod
    def validate_config(cls, config: ComponentConfig) -> Sequence[str]:
        """This method allows you to validate the configuration object received from the machine,
        as well as to return any implicit dependencies based on that `config`.

        Args:
            config (ComponentConfig): The configuration for this resource

        Returns:
            Sequence[str]: A list of implicit dependencies
        """
        return []

    def reconfigure(
        self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ):
        """This method allows you to dynamically update your service when it receives a new `config` object.

        Args:
            config (ComponentConfig): The new configuration
            dependencies (Mapping[ResourceName, ResourceBase]): Any dependencies (both implicit and explicit)
        """
        return super().reconfigure(config, dependencies)
    

    async def connect_machine(self):
        opts = RobotClient.Options.with_api_key( 
            api_key=os.getenv("API_KEY"),
            api_key_id=os.getenv("API_KEY_ID")
        )
        
        return await RobotClient.at_address('test-redish-main.8l4pdya4yy.viam.cloud', opts)
    
    async def connect_client(self) -> ViamClient:
        dial_options = DialOptions(
        credentials=Credentials(
            type="api-key",
            # Replace "<API-KEY>" (including brackets) with your machine's API key
            payload=os.getenv("API_KEY"),
        ),
        # Replace "<API-KEY-ID>" (including brackets) with your machine's
        # API key ID
        auth_entity=os.getenv("API_KEY_ID")
        )

        return await ViamClient.create_from_dial_options(dial_options)

    async def get_readings(
        self,
        *,
        extra: Optional[Mapping[str, Any]] = None,
        timeout: Optional[float] = None,
        **kwargs
    ) -> Mapping[str, SensorReading]:
        # Connect to machine
        if self.machine is None:
            self.machine = await self.connect_machine()

        # Connect to VIAM client
        if self.viam_client is None:
            self.viam_client = await self.connect_client()

        # Read GPIO pin from board
        # TODO: Add board name to config
        board_1 = Board.from_robot(self.machine, "board-1")
        button_pin = await board_1.gpio_pin_by_name("1") # Arbritrary pin value for testing
        button_pin_value = await button_pin.get()

        if button_pin_value:
            # TODO: Add camera names to config
            camera_names = ["camera-1", "camera-2", "camera-3", "camera-4"]
            for camera_name in camera_names:
                camera = Camera.from_robot(self.machine, camera_name)

                camera_image = await camera.get_image()
                camera_pil = viam_to_pil_image(camera_image)

                # Convert pillow image to binary
                binary_stream = BytesIO()
                camera_pil.save(binary_stream, format="JPEG")
                camera_bytes = binary_stream.getvalue()
                binary_stream.close()

                data_client = self.viam_client.data_client

                time_received = datetime.now()
                # TODO: Add time requested to config
                time_requested = time_received - timedelta(hours=1)

                try:
                    await data_client.binary_data_capture_upload(
                        part_id=os.getenv("PART_ID"),
                        binary_data=camera_bytes,
                        component_type="camera",
                        component_name=camera_name,
                        method_name="GetImage",
                        file_extension="jpeg",
                        data_request_times=[time_requested, time_received],
                    )
                except Exception as e:
                    raise Exception(f"Error uploading image: {e}")
            
        return {
            "button_pin_value": button_pin_value
            }


if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())

