from paddle import inference
c = inference.Config('a','b')
print('has set_tensorrt_optimization_level', hasattr(c, 'set_tensorrt_optimization_level'))
try:
    c.set_tensorrt_optimization_level(3)
    print('set_tensorrt_optimization_level ok')
except Exception as e:
    print('error calling set_tensorrt_optimization_level', e)
print('has tensorrt_optimization_level attr', hasattr(c, 'tensorrt_optimization_level'))
try:
    c.tensorrt_optimization_level = 3
    print('set attribute tensorrt_optimization_level ok')
except Exception as e:
    print('error setting attribute tensorrt_optimization_level', e)
